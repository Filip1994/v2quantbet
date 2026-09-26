"""Provider parsing for CardLab context observations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _identifier(prefix: str, payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return prefix + sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class FixtureContextObservation:
    context_observation_id: str
    fixture_id: str
    provider_fixture_id: int
    referee: str | None
    provider_status: str
    kickoff_at: datetime
    provider_updated_at: datetime | None
    available_at: datetime
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MatchStatisticsObservation:
    statistics_observation_id: str
    fixture_id: str
    provider_fixture_id: int
    home_fouls: int | None
    away_fouls: int | None
    home_yellow_cards: int | None
    away_yellow_cards: int | None
    home_red_cards: int | None
    away_red_cards: int | None
    home_second_yellow_cards: int | None
    away_second_yellow_cards: int | None
    home_corner_kicks: int | None
    away_corner_kicks: int | None
    home_ball_possession: float | None
    away_ball_possession: float | None
    home_shots_on_goal: int | None
    away_shots_on_goal: int | None
    home_shots_off_goal: int | None
    away_shots_off_goal: int | None
    home_total_shots: int | None
    away_total_shots: int | None
    home_blocked_shots: int | None
    away_blocked_shots: int | None
    home_shots_insidebox: int | None
    away_shots_insidebox: int | None
    home_shots_outsidebox: int | None
    away_shots_outsidebox: int | None
    home_offsides: int | None
    away_offsides: int | None
    home_goalkeeper_saves: int | None
    away_goalkeeper_saves: int | None
    home_total_passes: int | None
    away_total_passes: int | None
    home_passes_accurate: int | None
    away_passes_accurate: int | None
    home_pass_accuracy: float | None
    away_pass_accuracy: float | None
    available_at: datetime
    raw_payload: dict[str, Any]

    @property
    def fouls(self) -> int | None:
        if self.home_fouls is None or self.away_fouls is None:
            return None
        return self.home_fouls + self.away_fouls

    @property
    def yellow_cards(self) -> int | None:
        if self.home_yellow_cards is None or self.away_yellow_cards is None:
            return None
        return self.home_yellow_cards + self.away_yellow_cards

    @property
    def red_cards(self) -> int | None:
        if self.home_red_cards is None or self.away_red_cards is None:
            return None
        return self.home_red_cards + self.away_red_cards

    @property
    def second_yellow_cards(self) -> int | None:
        if self.home_second_yellow_cards is None or self.away_second_yellow_cards is None:
            return None
        return self.home_second_yellow_cards + self.away_second_yellow_cards


def parse_fixture_context(
    payload: Mapping[str, Any],
    *,
    fixture_id: str,
    provider_fixture_id: int,
    captured_at: datetime,
) -> FixtureContextObservation:
    captured = _utc(captured_at, "captured_at")
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")
    response = payload.get("response")
    if not isinstance(response, list) or not response:
        raise ValueError("fixture context response is empty")
    record = response[0]
    if not isinstance(record, Mapping):
        raise TypeError("fixture context record must be a mapping")
    fixture = record.get("fixture")
    if not isinstance(fixture, Mapping) or fixture.get("id") != provider_fixture_id:
        raise ValueError("fixture context does not match requested fixture")
    status = fixture.get("status")
    provider_status = (
        str(status.get("short") or status.get("long") or "").strip()
        if isinstance(status, Mapping)
        else ""
    )
    if not provider_status:
        provider_status = "UNKNOWN"
    kickoff = _parse_datetime(fixture.get("date"))
    if kickoff is None:
        timestamp = fixture.get("timestamp")
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
            kickoff = datetime.fromtimestamp(float(timestamp), tz=UTC)
    if kickoff is None:
        raise ValueError("fixture context kickoff is unavailable")
    referee = fixture.get("referee")
    referee_name = referee.strip() if isinstance(referee, str) and referee.strip() else None
    provider_updated_at = _parse_datetime(record.get("update") or fixture.get("update"))
    identity = {
        "fixture_id": fixture_id,
        "provider_fixture_id": provider_fixture_id,
        "referee": referee_name,
        "provider_status": provider_status,
        "kickoff_at": kickoff.isoformat(),
        "provider_updated_at": provider_updated_at.isoformat() if provider_updated_at else None,
        "available_at": captured.isoformat(),
    }
    return FixtureContextObservation(
        context_observation_id=_identifier("quantlab-context-v1:", identity),
        fixture_id=fixture_id,
        provider_fixture_id=provider_fixture_id,
        referee=referee_name,
        provider_status=provider_status,
        kickoff_at=kickoff,
        provider_updated_at=provider_updated_at,
        available_at=captured,
        raw_payload=dict(record),
    )


def _stat_value(record: Mapping[str, Any], stat_name: str) -> int | None:
    statistics = record.get("statistics")
    if not isinstance(statistics, list):
        return None
    for stat in statistics:
        if not isinstance(stat, Mapping):
            continue
        if str(stat.get("type") or "").strip().casefold() != stat_name.casefold():
            continue
        value = stat.get("value")
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None
    return None


def _stat_float(record: Mapping[str, Any], stat_name: str) -> float | None:
    statistics = record.get("statistics")
    if not isinstance(statistics, list):
        return None
    for stat in statistics:
        if not isinstance(stat, Mapping):
            continue
        if str(stat.get("type") or "").strip().casefold() != stat_name.casefold():
            continue
        value = stat.get("value")
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            raw = value.strip().removesuffix("%").strip()
            try:
                return float(raw)
            except ValueError:
                return None
        return None
    return None


def parse_fixture_statistics(
    payload: Mapping[str, Any],
    *,
    fixture_id: str,
    provider_fixture_id: int,
    home_team_id: int,
    away_team_id: int,
    captured_at: datetime,
) -> MatchStatisticsObservation:
    captured = _utc(captured_at, "captured_at")
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")
    response = payload.get("response")
    if not isinstance(response, list):
        raise TypeError("statistics response must contain a list")
    by_team: dict[int, Mapping[str, Any]] = {}
    for record in response:
        if not isinstance(record, Mapping):
            continue
        team = record.get("team")
        if isinstance(team, Mapping) and isinstance(team.get("id"), int):
            by_team[int(team["id"])] = record
    home = by_team.get(home_team_id)
    away = by_team.get(away_team_id)
    if home is None or away is None:
        raise ValueError("statistics response does not contain both fixture teams")

    values = {
        "home_fouls": _stat_value(home, "Fouls"),
        "away_fouls": _stat_value(away, "Fouls"),
        "home_yellow_cards": _stat_value(home, "Yellow Cards"),
        "away_yellow_cards": _stat_value(away, "Yellow Cards"),
        "home_red_cards": _stat_value(home, "Red Cards"),
        "away_red_cards": _stat_value(away, "Red Cards"),
        # API-Football's standard team-statistics response does not expose second-yellow
        # separately. Null means unknown/unavailable; it is never coerced to zero.
        "home_second_yellow_cards": None,
        "away_second_yellow_cards": None,
        "home_corner_kicks": _stat_value(home, "Corner Kicks"),
        "away_corner_kicks": _stat_value(away, "Corner Kicks"),
        "home_ball_possession": _stat_float(home, "Ball Possession"),
        "away_ball_possession": _stat_float(away, "Ball Possession"),
        "home_shots_on_goal": _stat_value(home, "Shots on Goal"),
        "away_shots_on_goal": _stat_value(away, "Shots on Goal"),
        "home_shots_off_goal": _stat_value(home, "Shots off Goal"),
        "away_shots_off_goal": _stat_value(away, "Shots off Goal"),
        "home_total_shots": _stat_value(home, "Total Shots"),
        "away_total_shots": _stat_value(away, "Total Shots"),
        "home_blocked_shots": _stat_value(home, "Blocked Shots"),
        "away_blocked_shots": _stat_value(away, "Blocked Shots"),
        "home_shots_insidebox": _stat_value(home, "Shots insidebox"),
        "away_shots_insidebox": _stat_value(away, "Shots insidebox"),
        "home_shots_outsidebox": _stat_value(home, "Shots outsidebox"),
        "away_shots_outsidebox": _stat_value(away, "Shots outsidebox"),
        "home_offsides": _stat_value(home, "Offsides"),
        "away_offsides": _stat_value(away, "Offsides"),
        "home_goalkeeper_saves": _stat_value(home, "Goalkeeper Saves"),
        "away_goalkeeper_saves": _stat_value(away, "Goalkeeper Saves"),
        "home_total_passes": _stat_value(home, "Total passes"),
        "away_total_passes": _stat_value(away, "Total passes"),
        "home_passes_accurate": _stat_value(home, "Passes accurate"),
        "away_passes_accurate": _stat_value(away, "Passes accurate"),
        "home_pass_accuracy": _stat_float(home, "Passes %"),
        "away_pass_accuracy": _stat_float(away, "Passes %"),
    }
    identity = {
        "fixture_id": fixture_id,
        "provider_fixture_id": provider_fixture_id,
        "available_at": captured.isoformat(),
        **values,
    }
    return MatchStatisticsObservation(
        statistics_observation_id=_identifier("quantlab-stats-v1:", identity),
        fixture_id=fixture_id,
        provider_fixture_id=provider_fixture_id,
        available_at=captured,
        raw_payload={"response": [dict(home), dict(away)]},
        **values,
    )
