"""Timestamp-safe GoalLab late-lineup context parsing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


LINEUP_FEATURE_VERSION = "GOALLAB_LATE_LINEUP_CONTEXT_V1"


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _team_id(record: dict[str, Any]) -> int | None:
    team = record.get("team")
    if not isinstance(team, dict):
        return None
    value = team.get("id")
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _player_ids(items: object) -> tuple[int, ...]:
    if not isinstance(items, list):
        return ()
    result: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        player = item.get("player")
        if not isinstance(player, dict):
            continue
        value = player.get("id")
        if isinstance(value, bool):
            continue
        try:
            player_id = int(value)
        except (TypeError, ValueError):
            continue
        if player_id > 0:
            result.append(player_id)
    return tuple(result)


def parse_goal_lineup_context(
    capture: dict[str, Any] | None,
    *,
    home_team_id: int,
    away_team_id: int,
    decision_at: datetime,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Return numeric late-context features plus categorical/player metadata.

    This parser does not inject formation strings into Structural DC+. It prepares a
    separately auditable late layer.
    """
    decision = _utc(decision_at, "decision_at")
    missing = {
        "lineup_coverage_flag": 0.0,
        "lineup_snapshot_age_minutes": float("nan"),
    }
    if capture is None:
        return missing, {
            "feature_version": LINEUP_FEATURE_VERSION,
            "quality": "UNAVAILABLE",
            "available_at": None,
        }

    available_raw = capture.get("available_at")
    if not isinstance(available_raw, datetime):
        return missing, {
            "feature_version": LINEUP_FEATURE_VERSION,
            "quality": "INVALID_TIMESTAMP",
            "available_at": None,
        }
    available = _utc(available_raw, "lineup.available_at")
    if available > decision:
        raise ValueError("lineup capture became available after decision_at")
    if capture.get("status") != "AVAILABLE":
        return missing, {
            "feature_version": LINEUP_FEATURE_VERSION,
            "quality": "UNAVAILABLE",
            "available_at": available.isoformat(),
            "reason": capture.get("reason"),
            "source": capture.get("source"),
        }

    payload = capture.get("raw_payload")
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, list):
        return missing, {
            "feature_version": LINEUP_FEATURE_VERSION,
            "quality": "INVALID_PAYLOAD",
            "available_at": available.isoformat(),
        }

    by_team: dict[int, dict[str, Any]] = {}
    for raw in response:
        if not isinstance(raw, dict):
            continue
        team_id = _team_id(raw)
        if team_id in {home_team_id, away_team_id}:
            by_team[team_id] = raw

    home = by_team.get(home_team_id)
    away = by_team.get(away_team_id)
    if home is None or away is None:
        return missing, {
            "feature_version": LINEUP_FEATURE_VERSION,
            "quality": "NOT_PUBLISHED",
            "available_at": available.isoformat(),
            "response_team_count": len(response),
        }

    home_xi = _player_ids(home.get("startXI"))
    away_xi = _player_ids(away.get("startXI"))
    home_bench = _player_ids(home.get("substitutes"))
    away_bench = _player_ids(away.get("substitutes"))
    home_formation = home.get("formation") if isinstance(home.get("formation"), str) else None
    away_formation = away.get("formation") if isinstance(away.get("formation"), str) else None

    numeric = {
        "lineup_coverage_flag": 1.0,
        "lineup_snapshot_age_minutes": max(
            0.0, (decision - available).total_seconds() / 60.0
        ),
        "home_starting_xi_count": float(len(home_xi)),
        "away_starting_xi_count": float(len(away_xi)),
        "home_bench_count": float(len(home_bench)),
        "away_bench_count": float(len(away_bench)),
        "starting_xi_count_differential": float(len(home_xi) - len(away_xi)),
        "bench_count_differential": float(len(home_bench) - len(away_bench)),
    }
    return numeric, {
        "feature_version": LINEUP_FEATURE_VERSION,
        "quality": "OBSERVED",
        "available_at": available.isoformat(),
        "source": capture.get("source"),
        "home_formation": home_formation,
        "away_formation": away_formation,
        "home_starting_player_ids": home_xi,
        "away_starting_player_ids": away_xi,
        "home_bench_player_ids": home_bench,
        "away_bench_player_ids": away_bench,
    }
