"""Timestamp-safe GoalLab standings feature extraction."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from typing import Any


STANDINGS_FEATURE_VERSION = "GOALLAB_STANDINGS_FEATURES_V1"


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _standings_groups(payload: dict[str, Any] | None) -> list[list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        return []
    response = payload.get("response")
    if not isinstance(response, list):
        return []
    groups: list[list[dict[str, Any]]] = []
    for record in response:
        if not isinstance(record, dict):
            continue
        league = record.get("league")
        if not isinstance(league, dict):
            continue
        raw_groups = league.get("standings")
        if not isinstance(raw_groups, list):
            continue
        for raw_group in raw_groups:
            if not isinstance(raw_group, list):
                continue
            rows = [row for row in raw_group if isinstance(row, dict)]
            if rows:
                groups.append(rows)
    return groups


def _group_for_teams(
    payload: dict[str, Any] | None,
    home_team_id: int,
    away_team_id: int,
) -> list[dict[str, Any]] | None:
    for rows in _standings_groups(payload):
        ids = {
            int(team["id"])
            for row in rows
            if isinstance((team := row.get("team")), dict)
            and isinstance(team.get("id"), int)
        }
        if home_team_id in ids and away_team_id in ids:
            return rows
    return None


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, float | int]]:
    normalized: list[dict[str, float | int]] = []
    for row in rows:
        team = row.get("team")
        rank = row.get("rank")
        points = _number(row.get("points"))
        if (
            not isinstance(team, dict)
            or not isinstance(team.get("id"), int)
            or not isinstance(rank, int)
            or rank <= 0
            or points is None
        ):
            continue
        all_stats = row.get("all")
        played = (
            _number(all_stats.get("played")) if isinstance(all_stats, dict) else None
        )
        goal_diff = _number(row.get("goalsDiff"))
        if goal_diff is None and isinstance(all_stats, dict):
            goals = all_stats.get("goals")
            if isinstance(goals, dict):
                gf = _number(goals.get("for"))
                ga = _number(goals.get("against"))
                if gf is not None and ga is not None:
                    goal_diff = gf - ga
        normalized.append(
            {
                "team_id": int(team["id"]),
                "rank": rank,
                "points": points,
                "played": 0.0 if played is None else played,
                "goal_difference": 0.0 if goal_diff is None else goal_diff,
            }
        )
    normalized.sort(key=lambda item: int(item["rank"]))
    return normalized


def _second_tier(competition_name: str) -> bool:
    name = competition_name.casefold()
    return any(
        token in name
        for token in (
            "championship",
            "serie b",
            "segunda",
            "2. bundesliga",
            "2 bundesliga",
            "ligue 2",
        )
    )


def _threshold_ranks(n: int, competition_name: str) -> tuple[int, int, int]:
    if _second_tier(competition_name):
        primary = min(2, n)
    else:
        primary = min(4, n)
    return 1, primary, max(1, n - 2)


def _pressure(
    points: float,
    *,
    leader_points: float,
    primary_points: float,
    relegation_points: float,
) -> float:
    distances = (
        abs(leader_points - points),
        abs(primary_points - points),
        abs(points - relegation_points),
    )
    return 1.0 / (1.0 + min(distances))


def _team_features(
    own: dict[str, float | int],
    *,
    n: int,
    leader_points: float,
    primary_points: float,
    relegation_points: float,
) -> dict[str, float]:
    rank = float(own["rank"])
    points = float(own["points"])
    played = float(own["played"])
    goal_difference = float(own["goal_difference"])
    ppg = points / played if played > 0 else float("nan")
    rank_percentile = (
        1.0 if n <= 1 else 1.0 - (rank - 1.0) / float(n - 1)
    )
    return {
        "rank": rank,
        "points": points,
        "ppg": ppg,
        "goal_difference": goal_difference,
        "rank_percentile": rank_percentile,
        "distance_to_title_points": leader_points - points,
        "distance_to_primary_threshold_points": primary_points - points,
        "distance_to_relegation_points": points - relegation_points,
        "table_pressure": _pressure(
            points,
            leader_points=leader_points,
            primary_points=primary_points,
            relegation_points=relegation_points,
        ),
        "played": played,
    }


def build_goal_standings_features(
    payload: dict[str, Any] | None,
    *,
    home_team_id: int,
    away_team_id: int,
    competition_name: str,
    available_at: datetime | None,
    decision_at: datetime,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Return raw standings covariates and timestamp/provenance metadata."""
    decision = _utc(decision_at, "decision_at")
    missing = {
        "standings_coverage_flag": 0.0,
        "standings_snapshot_age_days": float("nan"),
    }
    if payload is None or available_at is None:
        return missing, {
            "feature_version": STANDINGS_FEATURE_VERSION,
            "quality": "UNAVAILABLE",
            "available_at": None,
        }

    available = _utc(available_at, "standings.available_at")
    if available > decision:
        raise ValueError("standings snapshot became available after decision_at")
    rows = _group_for_teams(payload, home_team_id, away_team_id)
    if not rows:
        return missing, {
            "feature_version": STANDINGS_FEATURE_VERSION,
            "quality": "TEAMS_NOT_IN_SAME_TABLE",
            "available_at": available.isoformat(),
        }
    normalized = _normalize_rows(rows)
    home = next(
        (row for row in normalized if int(row["team_id"]) == home_team_id),
        None,
    )
    away = next(
        (row for row in normalized if int(row["team_id"]) == away_team_id),
        None,
    )
    if home is None or away is None or len(normalized) < 4:
        return missing, {
            "feature_version": STANDINGS_FEATURE_VERSION,
            "quality": "INSUFFICIENT_TABLE",
            "available_at": available.isoformat(),
        }

    by_rank = {int(row["rank"]): row for row in normalized}
    title_rank, primary_rank, relegation_rank = _threshold_ranks(
        len(normalized), competition_name
    )
    leader_points = float(by_rank[title_rank]["points"])
    primary_points = float(by_rank[primary_rank]["points"])
    relegation_points = float(by_rank[relegation_rank]["points"])
    home_features = _team_features(
        home,
        n=len(normalized),
        leader_points=leader_points,
        primary_points=primary_points,
        relegation_points=relegation_points,
    )
    away_features = _team_features(
        away,
        n=len(normalized),
        leader_points=leader_points,
        primary_points=primary_points,
        relegation_points=relegation_points,
    )

    expected_matches = max(1.0, 2.0 * (len(normalized) - 1))
    season_progress = min(
        1.0,
        max(
            0.0,
            (home_features["played"] + away_features["played"])
            / (2.0 * expected_matches),
        ),
    )
    features: dict[str, float] = {
        "standings_coverage_flag": 1.0,
        "standings_snapshot_age_days": max(
            0.0, (decision - available).total_seconds() / 86_400.0
        ),
        "home_standings_rank": home_features["rank"],
        "away_standings_rank": away_features["rank"],
        "standings_rank_differential": home_features["rank"] - away_features["rank"],
        "home_standings_points": home_features["points"],
        "away_standings_points": away_features["points"],
        "standings_points_differential": home_features["points"] - away_features["points"],
        "home_standings_ppg": home_features["ppg"],
        "away_standings_ppg": away_features["ppg"],
        "standings_ppg_differential": home_features["ppg"] - away_features["ppg"],
        "home_standings_goal_difference": home_features["goal_difference"],
        "away_standings_goal_difference": away_features["goal_difference"],
        "standings_goal_difference_differential": (
            home_features["goal_difference"] - away_features["goal_difference"]
        ),
        "home_rank_percentile": home_features["rank_percentile"],
        "away_rank_percentile": away_features["rank_percentile"],
        "home_distance_to_title_points": home_features["distance_to_title_points"],
        "away_distance_to_title_points": away_features["distance_to_title_points"],
        "home_distance_to_primary_threshold_points": home_features[
            "distance_to_primary_threshold_points"
        ],
        "away_distance_to_primary_threshold_points": away_features[
            "distance_to_primary_threshold_points"
        ],
        "home_distance_to_relegation_points": home_features[
            "distance_to_relegation_points"
        ],
        "away_distance_to_relegation_points": away_features[
            "distance_to_relegation_points"
        ],
        "home_table_pressure": home_features["table_pressure"],
        "away_table_pressure": away_features["table_pressure"],
        "table_pressure_differential": (
            home_features["table_pressure"] - away_features["table_pressure"]
        ),
        "season_progress": season_progress,
        "match_importance_proxy": max(
            home_features["table_pressure"], away_features["table_pressure"]
        )
        * season_progress,
        "both_teams_high_pressure_interaction": (
            home_features["table_pressure"] * away_features["table_pressure"]
        ),
        "table_pressure_diff_x_season_progress": (
            home_features["table_pressure"] - away_features["table_pressure"]
        )
        * season_progress,
    }
    return features, {
        "feature_version": STANDINGS_FEATURE_VERSION,
        "quality": "OBSERVED",
        "available_at": available.isoformat(),
        "table_size": len(normalized),
        "title_rank": title_rank,
        "primary_threshold_rank": primary_rank,
        "relegation_threshold_rank": relegation_rank,
    }
