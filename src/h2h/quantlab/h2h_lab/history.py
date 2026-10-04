"""Timestamp-safe direct H2H parsing for H2HLab V1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

FINAL_STATUSES = {"FT", "AET", "PEN"}


def _kickoff(raw: Mapping[str, Any]) -> datetime | None:
    fixture = raw.get("fixture")
    if not isinstance(fixture, Mapping):
        return None
    value = fixture.get("date")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _score(raw: Mapping[str, Any]) -> tuple[int, int] | None:
    score = raw.get("score")
    if isinstance(score, Mapping):
        fulltime = score.get("fulltime")
        if isinstance(fulltime, Mapping):
            home, away = fulltime.get("home"), fulltime.get("away")
            if isinstance(home, int) and not isinstance(home, bool) and isinstance(away, int) and not isinstance(away, bool):
                return home, away
    goals = raw.get("goals")
    if isinstance(goals, Mapping):
        home, away = goals.get("home"), goals.get("away")
        if isinstance(home, int) and not isinstance(home, bool) and isinstance(away, int) and not isinstance(away, bool):
            return home, away
    return None


def parse_h2h_response(
    payload: Mapping[str, Any],
    *,
    target_home_team_id: int,
    target_away_team_id: int,
    before: datetime,
    maximum: int = 10,
) -> tuple[dict[str, Any], ...]:
    if maximum < 5 or maximum > 10:
        raise ValueError("maximum H2H history must be between 5 and 10")
    if before.tzinfo is None or before.utcoffset() is None:
        raise ValueError("before must be timezone-aware")
    response = payload.get("response", [])
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise TypeError("H2H response must be a list")
    allowed = {target_home_team_id, target_away_team_id}
    rows: list[dict[str, Any]] = []
    for raw in response:
        if not isinstance(raw, Mapping):
            continue
        fixture = raw.get("fixture")
        teams = raw.get("teams")
        if not isinstance(fixture, Mapping) or not isinstance(teams, Mapping):
            continue
        status = fixture.get("status")
        short = status.get("short") if isinstance(status, Mapping) else None
        if short not in FINAL_STATUSES:
            continue
        kickoff = _kickoff(raw)
        if kickoff is None or kickoff >= before.astimezone(UTC):
            continue
        home = teams.get("home")
        away = teams.get("away")
        if not isinstance(home, Mapping) or not isinstance(away, Mapping):
            continue
        home_id, away_id = home.get("id"), away.get("id")
        if not isinstance(home_id, int) or not isinstance(away_id, int):
            continue
        if {home_id, away_id} != allowed:
            continue
        score = _score(raw)
        if score is None:
            continue
        home_goals, away_goals = score
        league = raw.get("league")
        rows.append(
            {
                "provider_fixture_id": fixture.get("id"),
                "kickoff_at": kickoff.isoformat(),
                "home_team_id": home_id,
                "away_team_id": away_id,
                "home_team": home.get("name"),
                "away_team": away.get("name"),
                "home_goals": home_goals,
                "away_goals": away_goals,
                "competition_name": league.get("name") if isinstance(league, Mapping) else None,
                "league_id": league.get("id") if isinstance(league, Mapping) else None,
            }
        )
    rows.sort(key=lambda item: item["kickoff_at"], reverse=True)
    return tuple(rows[:maximum])
