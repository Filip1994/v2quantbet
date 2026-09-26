"""Timestamp-safe GoalLab target injury/suspension features."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from typing import Any


INJURY_FEATURE_VERSION = "GOALLAB_INJURY_FEATURES_V1"

_SUSPENSION_TOKENS = (
    "suspension",
    "suspended",
    "red card",
    "yellow card",
    "cards",
    "disciplinary",
)


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _safe_team_id(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _classify_absence(record: dict[str, Any]) -> str:
    player = record.get("player")
    text_parts: list[str] = []
    if isinstance(player, dict):
        for key in ("type", "reason"):
            value = player.get(key)
            if isinstance(value, str):
                text_parts.append(value.casefold())
    text = " ".join(text_parts)
    if any(token in text for token in _SUSPENSION_TOKENS):
        return "SUSPENSION"
    return "INJURY_OR_OTHER"


def build_goal_injury_features(
    capture: dict[str, Any] | None,
    *,
    home_team_id: int,
    away_team_id: int,
    decision_at: datetime,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Build target availability counts from one pre-decision injury capture.

    A valid AVAILABLE empty response means zero absences. Missing/UNAVAILABLE capture
    means unknown and does not fabricate zeros.
    """
    decision = _utc(decision_at, "decision_at")
    missing = {
        "injury_coverage_flag": 0.0,
        "injury_snapshot_age_days": float("nan"),
    }
    if capture is None:
        return missing, {
            "feature_version": INJURY_FEATURE_VERSION,
            "quality": "UNAVAILABLE",
            "available_at": None,
        }

    available_raw = capture.get("available_at")
    if not isinstance(available_raw, datetime):
        return missing, {
            "feature_version": INJURY_FEATURE_VERSION,
            "quality": "INVALID_TIMESTAMP",
            "available_at": None,
        }
    available = _utc(available_raw, "injuries.available_at")
    if available > decision:
        raise ValueError("injury capture became available after decision_at")
    if capture.get("status") != "AVAILABLE":
        return missing, {
            "feature_version": INJURY_FEATURE_VERSION,
            "quality": "UNAVAILABLE",
            "available_at": available.isoformat(),
            "reason": capture.get("reason"),
            "source": capture.get("source"),
        }

    payload = capture.get("raw_payload")
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, list):
        return missing, {
            "feature_version": INJURY_FEATURE_VERSION,
            "quality": "INVALID_PAYLOAD",
            "available_at": available.isoformat(),
            "source": capture.get("source"),
        }

    counts = {
        home_team_id: {"unavailable": 0, "injuries": 0, "suspensions": 0},
        away_team_id: {"unavailable": 0, "injuries": 0, "suspensions": 0},
    }
    used_players: dict[int, set[int]] = {home_team_id: set(), away_team_id: set()}
    unknown_team_records = 0
    for raw in response:
        if not isinstance(raw, dict):
            continue
        team = raw.get("team")
        player = raw.get("player")
        team_id = (
            _safe_team_id(team.get("id")) if isinstance(team, dict) else None
        )
        player_id = (
            _safe_team_id(player.get("id")) if isinstance(player, dict) else None
        )
        if team_id not in counts:
            unknown_team_records += 1
            continue
        if player_id is not None and player_id in used_players[team_id]:
            continue
        if player_id is not None:
            used_players[team_id].add(player_id)
        counts[team_id]["unavailable"] += 1
        classification = _classify_absence(raw)
        if classification == "SUSPENSION":
            counts[team_id]["suspensions"] += 1
        else:
            counts[team_id]["injuries"] += 1

    home = counts[home_team_id]
    away = counts[away_team_id]
    features = {
        "injury_coverage_flag": 1.0,
        "injury_snapshot_age_days": max(
            0.0, (decision - available).total_seconds() / 86_400.0
        ),
        "home_unavailable_player_count": float(home["unavailable"]),
        "away_unavailable_player_count": float(away["unavailable"]),
        "unavailable_count_differential": float(
            home["unavailable"] - away["unavailable"]
        ),
        "home_injury_count": float(home["injuries"]),
        "away_injury_count": float(away["injuries"]),
        "home_suspension_count": float(home["suspensions"]),
        "away_suspension_count": float(away["suspensions"]),
    }
    return features, {
        "feature_version": INJURY_FEATURE_VERSION,
        "quality": "OBSERVED",
        "available_at": available.isoformat(),
        "source": capture.get("source"),
        "response_item_count": len(response),
        "home_unique_players": len(used_players[home_team_id]),
        "away_unique_players": len(used_players[away_team_id]),
        "unknown_team_records": unknown_team_records,
        "classification_rule": "reason/type token classifier for suspension; other absences remain injury_or_other",
    }
