"""Timestamp-safe GoalLab manager/coach context features."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any


MANAGER_FEATURE_VERSION = "GOALLAB_MANAGER_FEATURES_V1"
RECENT_MANAGER_MATCH_THRESHOLD = 5


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _team_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _active_coach_context(
    capture: dict[str, Any] | None,
    *,
    team_id: int,
    decision_at: datetime,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    decision = _utc(decision_at, "decision_at")
    if capture is None:
        return None, {
            "quality": "UNAVAILABLE",
            "available_at": None,
        }
    available_raw = capture.get("available_at")
    if not isinstance(available_raw, datetime):
        return None, {
            "quality": "INVALID_TIMESTAMP",
            "available_at": None,
        }
    available = _utc(available_raw, "coach.available_at")
    if available > decision:
        raise ValueError("coach capture became available after decision_at")
    if capture.get("status") != "AVAILABLE":
        return None, {
            "quality": "UNAVAILABLE",
            "available_at": available.isoformat(),
            "reason": capture.get("reason"),
        }

    payload = capture.get("raw_payload")
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, list):
        return None, {
            "quality": "INVALID_PAYLOAD",
            "available_at": available.isoformat(),
        }

    candidates: list[tuple[date, dict[str, Any], dict[str, Any]]] = []
    for raw in response:
        if not isinstance(raw, dict):
            continue
        career = raw.get("career")
        if not isinstance(career, list):
            continue
        for entry in career:
            if not isinstance(entry, dict):
                continue
            team = entry.get("team")
            entry_team_id = (
                _team_id(team.get("id")) if isinstance(team, dict) else None
            )
            if entry_team_id != team_id:
                continue
            start = _parse_date(entry.get("start"))
            end = _parse_date(entry.get("end"))
            if start is None or start > decision.date():
                continue
            if end is not None and end < decision.date():
                continue
            candidates.append((start, raw, entry))

    if not candidates:
        return None, {
            "quality": "NO_ACTIVE_COACH",
            "available_at": available.isoformat(),
            "response_item_count": len(response),
        }

    start, raw, _entry = max(candidates, key=lambda item: item[0])
    coach_id = _team_id(raw.get("id"))
    name = raw.get("name") if isinstance(raw.get("name"), str) else None
    tenure_days = float((decision.date() - start).days)
    return {
        "coach_id": coach_id,
        "name": name,
        "start_date": start,
        "tenure_days": max(0.0, tenure_days),
        "capture_id": capture.get("coach_capture_id"),
        "available_at": available,
    }, {
        "quality": "OBSERVED",
        "available_at": available.isoformat(),
        "coach_id": coach_id,
        "coach_name": name,
        "start_date": start.isoformat(),
    }


def _matches_since(
    match_dates: list[datetime],
    *,
    start_date: date,
    decision_at: datetime,
) -> int:
    decision = _utc(decision_at, "decision_at")
    return sum(
        item.astimezone(UTC) < decision and item.astimezone(UTC).date() >= start_date
        for item in match_dates
    )


def build_goal_manager_features(
    home_capture: dict[str, Any] | None,
    away_capture: dict[str, Any] | None,
    *,
    home_team_id: int,
    away_team_id: int,
    home_match_dates: list[datetime],
    away_match_dates: list[datetime],
    decision_at: datetime,
) -> tuple[dict[str, float], dict[str, Any]]:
    home, home_meta = _active_coach_context(
        home_capture,
        team_id=home_team_id,
        decision_at=decision_at,
    )
    away, away_meta = _active_coach_context(
        away_capture,
        team_id=away_team_id,
        decision_at=decision_at,
    )

    features: dict[str, float] = {
        "home_manager_coverage_flag": float(home is not None),
        "away_manager_coverage_flag": float(away is not None),
        "manager_coverage_flag": float(home is not None and away is not None),
    }
    if home is not None:
        home_matches = _matches_since(
            home_match_dates,
            start_date=home["start_date"],
            decision_at=decision_at,
        )
        features.update(
            {
                "home_manager_tenure_days": float(home["tenure_days"]),
                "home_matches_under_manager": float(home_matches),
                "home_recent_manager_change_flag": float(
                    home_matches < RECENT_MANAGER_MATCH_THRESHOLD
                ),
            }
        )
    if away is not None:
        away_matches = _matches_since(
            away_match_dates,
            start_date=away["start_date"],
            decision_at=decision_at,
        )
        features.update(
            {
                "away_manager_tenure_days": float(away["tenure_days"]),
                "away_matches_under_manager": float(away_matches),
                "away_recent_manager_change_flag": float(
                    away_matches < RECENT_MANAGER_MATCH_THRESHOLD
                ),
            }
        )
    if home is not None and away is not None:
        features["manager_tenure_differential"] = (
            float(home["tenure_days"]) - float(away["tenure_days"])
        )
        features["both_new_manager_interaction"] = (
            features["home_recent_manager_change_flag"]
            * features["away_recent_manager_change_flag"]
        )

    return features, {
        "feature_version": MANAGER_FEATURE_VERSION,
        "recent_manager_rule": (
            f"fewer_than_{RECENT_MANAGER_MATCH_THRESHOLD}_prior_team_matches_since_start"
        ),
        "home": home_meta,
        "away": away_meta,
    }
