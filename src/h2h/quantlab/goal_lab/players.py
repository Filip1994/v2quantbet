"""Historical player-form aggregation for GoalLab DC+ Structural."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any


PLAYER_FEATURE_VERSION = "GOALLAB_PLAYER_FORM_FEATURES_V1"
RECENT_TEAM_MATCHES = 10
RECENT_PLAYER_APPEARANCES = 5
PROJECTED_XI_SIZE = 11


@dataclass(frozen=True, slots=True)
class PlayerMatchSample:
    fixture_id: str
    kickoff_at: datetime
    team_id: int
    player_id: int
    minutes: float
    starter: bool | None
    position: str | None
    rating: float | None
    shots: float
    shots_on_target: float
    goals: float
    assists: float
    key_passes: float
    tackles: float
    interceptions: float
    duels: float
    duels_won: float


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _nonnegative(value: object) -> float:
    parsed = _number(value)
    return 0.0 if parsed is None or parsed < 0 else parsed


def _id(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _nested(mapping: object, *keys: str) -> object:
    value = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def parse_goal_player_match_samples(
    payload: dict[str, Any] | None,
    *,
    fixture_id: str,
    kickoff_at: datetime,
    eligible_team_ids: set[int],
) -> tuple[PlayerMatchSample, ...]:
    """Parse one completed fixture /fixtures/players payload."""
    if not isinstance(kickoff_at, datetime):
        raise TypeError("kickoff_at must be datetime")
    kickoff = kickoff_at.astimezone(UTC)
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, list):
        return ()

    result: list[PlayerMatchSample] = []
    seen: set[tuple[int, int]] = set()
    for team_record in response:
        if not isinstance(team_record, dict):
            continue
        team_id = _id(_nested(team_record, "team", "id"))
        if team_id not in eligible_team_ids:
            continue
        players = team_record.get("players")
        if not isinstance(players, list):
            continue
        for player_record in players:
            if not isinstance(player_record, dict):
                continue
            player_id = _id(_nested(player_record, "player", "id"))
            if player_id is None or (team_id, player_id) in seen:
                continue
            stats_list = player_record.get("statistics")
            if not isinstance(stats_list, list):
                continue
            stats = next((item for item in stats_list if isinstance(item, dict)), None)
            if stats is None:
                continue
            minutes = _nonnegative(_nested(stats, "games", "minutes"))
            if minutes <= 0:
                continue
            substitute_raw = _nested(stats, "games", "substitute")
            starter = (
                None
                if not isinstance(substitute_raw, bool)
                else not substitute_raw
            )
            position_raw = _nested(stats, "games", "position")
            position = position_raw if isinstance(position_raw, str) else None
            rating = _number(_nested(stats, "games", "rating"))
            seen.add((team_id, player_id))
            result.append(
                PlayerMatchSample(
                    fixture_id=fixture_id,
                    kickoff_at=kickoff,
                    team_id=team_id,
                    player_id=player_id,
                    minutes=minutes,
                    starter=starter,
                    position=position,
                    rating=rating,
                    shots=_nonnegative(_nested(stats, "shots", "total")),
                    shots_on_target=_nonnegative(_nested(stats, "shots", "on")),
                    goals=_nonnegative(_nested(stats, "goals", "total")),
                    assists=_nonnegative(_nested(stats, "goals", "assists")),
                    key_passes=_nonnegative(_nested(stats, "passes", "key")),
                    tackles=_nonnegative(_nested(stats, "tackles", "total")),
                    interceptions=_nonnegative(_nested(stats, "tackles", "interceptions")),
                    duels=_nonnegative(_nested(stats, "duels", "total")),
                    duels_won=_nonnegative(_nested(stats, "duels", "won")),
                )
            )
    return tuple(result)


def _recent_team_fixture_ids(
    samples: list[PlayerMatchSample],
    *,
    target_kickoff: datetime,
) -> tuple[str, ...]:
    fixtures: list[str] = []
    seen: set[str] = set()
    for item in reversed(samples):
        if item.kickoff_at >= target_kickoff or item.fixture_id in seen:
            continue
        seen.add(item.fixture_id)
        fixtures.append(item.fixture_id)
        if len(fixtures) >= RECENT_TEAM_MATCHES:
            break
    return tuple(fixtures)


def _projected_players(
    samples: list[PlayerMatchSample],
    *,
    target_kickoff: datetime,
) -> tuple[int, ...]:
    fixture_ids = set(_recent_team_fixture_ids(samples, target_kickoff=target_kickoff))
    by_player: dict[int, list[PlayerMatchSample]] = {}
    for item in samples:
        if item.fixture_id not in fixture_ids or item.kickoff_at >= target_kickoff:
            continue
        by_player.setdefault(item.player_id, []).append(item)

    ranked: list[tuple[tuple[float, ...], int]] = []
    for player_id, history in by_player.items():
        starts = float(sum(item.starter is True for item in history))
        appearances = float(len(history))
        minutes = float(sum(item.minutes for item in history))
        last_at = max(item.kickoff_at for item in history).timestamp()
        # Lexicographic availability projection; no football-effect coefficient.
        rank = (starts, appearances, minutes, last_at, float(-player_id))
        ranked.append((rank, player_id))
    ranked.sort(reverse=True)
    return tuple(player_id for _rank, player_id in ranked[:PROJECTED_XI_SIZE])


def _per90(total: float, minutes: float) -> float:
    return 0.0 if minutes <= 0 else total * 90.0 / minutes


def _player_recent(
    samples: list[PlayerMatchSample],
    player_id: int,
    *,
    target_kickoff: datetime,
) -> list[PlayerMatchSample]:
    eligible = [
        item
        for item in samples
        if item.player_id == player_id and item.kickoff_at < target_kickoff
    ]
    eligible.sort(key=lambda item: (item.kickoff_at, item.fixture_id))
    return eligible[-RECENT_PLAYER_APPEARANCES:]


def projected_team_player_features(
    samples: list[PlayerMatchSample],
    *,
    prefix: str,
    target_kickoff: datetime,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Project a likely XI from prior participation and aggregate recent player form."""
    projected = _projected_players(samples, target_kickoff=target_kickoff)
    if not projected:
        return {
            f"{prefix}_player_stats_coverage_flag": 0.0,
            f"{prefix}_projected_xi_count": 0.0,
        }, {
            "feature_version": PLAYER_FEATURE_VERSION,
            "quality": "NO_PLAYER_HISTORY",
            "projected_player_ids": (),
        }

    player_rows: list[dict[str, float | int | str | None]] = []
    rating_weighted_sum = 0.0
    rating_minutes = 0.0
    total_minutes = 0.0
    totals = {
        "shots": 0.0,
        "sot": 0.0,
        "goals": 0.0,
        "assists": 0.0,
        "key_passes": 0.0,
        "defensive_actions": 0.0,
        "duels": 0.0,
        "duels_won": 0.0,
    }
    xi_per90 = {
        "shots": 0.0,
        "sot": 0.0,
        "goals_assists": 0.0,
        "key_passes": 0.0,
        "defensive_actions": 0.0,
    }
    creator_by_player: list[float] = []
    goals_by_player: list[float] = []

    for player_id in projected:
        history = _player_recent(samples, player_id, target_kickoff=target_kickoff)
        if not history:
            continue
        minutes = float(sum(item.minutes for item in history))
        total_minutes += minutes
        player_totals = {
            "shots": float(sum(item.shots for item in history)),
            "sot": float(sum(item.shots_on_target for item in history)),
            "goals": float(sum(item.goals for item in history)),
            "assists": float(sum(item.assists for item in history)),
            "key_passes": float(sum(item.key_passes for item in history)),
            "defensive_actions": float(
                sum(item.tackles + item.interceptions for item in history)
            ),
            "duels": float(sum(item.duels for item in history)),
            "duels_won": float(sum(item.duels_won for item in history)),
        }
        for key, value in player_totals.items():
            totals[key] += value
        xi_per90["shots"] += _per90(player_totals["shots"], minutes)
        xi_per90["sot"] += _per90(player_totals["sot"], minutes)
        xi_per90["goals_assists"] += _per90(
            player_totals["goals"] + player_totals["assists"],
            minutes,
        )
        xi_per90["key_passes"] += _per90(player_totals["key_passes"], minutes)
        xi_per90["defensive_actions"] += _per90(
            player_totals["defensive_actions"],
            minutes,
        )

        ratings = [
            (item.rating, item.minutes)
            for item in history
            if item.rating is not None and item.minutes > 0
        ]
        if ratings:
            rating_weighted_sum += sum(float(rating) * minutes for rating, minutes in ratings)
            rating_minutes += sum(minutes for _rating, minutes in ratings)

        creator_by_player.append(player_totals["key_passes"])
        goals_by_player.append(player_totals["goals"])
        player_rows.append(
            {
                "player_id": player_id,
                "appearances": len(history),
                "minutes": minutes,
                "position": next(
                    (item.position for item in reversed(history) if item.position),
                    None,
                ),
                "goals": player_totals["goals"],
                "assists": player_totals["assists"],
                "key_passes": player_totals["key_passes"],
            }
        )

    if not player_rows or total_minutes <= 0:
        return {
            f"{prefix}_player_stats_coverage_flag": 0.0,
            f"{prefix}_projected_xi_count": float(len(projected)),
        }, {
            "feature_version": PLAYER_FEATURE_VERSION,
            "quality": "INSUFFICIENT_PLAYER_HISTORY",
            "projected_player_ids": projected,
        }

    creator_total = sum(creator_by_player)
    scorer_total = sum(goals_by_player)
    features = {
        f"{prefix}_player_stats_coverage_flag": 1.0,
        f"{prefix}_projected_xi_count": float(len(player_rows)),
        f"{prefix}_projected_xi_rolling_rating": (
            float("nan")
            if rating_minutes <= 0
            else rating_weighted_sum / rating_minutes
        ),
        f"{prefix}_projected_xi_shots_per90": xi_per90["shots"],
        f"{prefix}_projected_xi_sot_per90": xi_per90["sot"],
        f"{prefix}_projected_xi_key_passes_per90": xi_per90["key_passes"],
        f"{prefix}_projected_xi_goals_assists_per90": xi_per90["goals_assists"],
        f"{prefix}_projected_xi_defensive_actions_per90": xi_per90[
            "defensive_actions"
        ],
        f"{prefix}_projected_xi_duel_win_rate": (
            float("nan") if totals["duels"] <= 0 else totals["duels_won"] / totals["duels"]
        ),
        f"{prefix}_creator_concentration": (
            0.0 if creator_total <= 0 else max(creator_by_player) / creator_total
        ),
        f"{prefix}_scorer_concentration": (
            0.0 if scorer_total <= 0 else max(goals_by_player) / scorer_total
        ),
    }
    return features, {
        "feature_version": PLAYER_FEATURE_VERSION,
        "quality": "OBSERVED",
        "projection_rule": (
            "top_11_lexicographic_prior_starts_appearances_minutes_recency"
        ),
        "recent_team_matches": RECENT_TEAM_MATCHES,
        "recent_player_appearances": RECENT_PLAYER_APPEARANCES,
        "projected_player_ids": tuple(int(item["player_id"]) for item in player_rows),
        "players": player_rows,
    }


def build_projected_match_player_features(
    histories: dict[int, list[PlayerMatchSample]],
    *,
    home_team_id: int,
    away_team_id: int,
    target_kickoff: datetime,
) -> tuple[dict[str, float], dict[str, Any]]:
    home, home_meta = projected_team_player_features(
        histories.get(home_team_id, []),
        prefix="home",
        target_kickoff=target_kickoff,
    )
    away, away_meta = projected_team_player_features(
        histories.get(away_team_id, []),
        prefix="away",
        target_kickoff=target_kickoff,
    )
    features = {**home, **away}
    home_rating = features.get("home_projected_xi_rolling_rating")
    away_rating = features.get("away_projected_xi_rolling_rating")
    if (
        home_rating is not None
        and away_rating is not None
        and isfinite(home_rating)
        and isfinite(away_rating)
    ):
        features["player_quality_differential"] = home_rating - away_rating
    features["player_stats_coverage_flag"] = float(
        features.get("home_player_stats_coverage_flag") == 1.0
        and features.get("away_player_stats_coverage_flag") == 1.0
    )
    return features, {
        "feature_version": PLAYER_FEATURE_VERSION,
        "home": home_meta,
        "away": away_meta,
    }
