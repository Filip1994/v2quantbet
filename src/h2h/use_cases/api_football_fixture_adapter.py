"""Translate API-Football fixture payloads into canonical fixtures."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from h2h.domain.fixture import Fixture


class ApiFootballFixtureAdapter:
    """Convert one API-Football fixture object into a canonical ``Fixture``."""

    def adapt(self, payload: Mapping[str, Any]) -> Fixture:
        """Translate a provider fixture payload without leaking provider fields."""
        fixture = self._mapping(payload, "fixture")
        teams = self._mapping(payload, "teams")
        home = self._mapping(teams, "home")
        away = self._mapping(teams, "away")
        league = self._mapping(payload, "league")

        kickoff = fixture.get("date")
        if not isinstance(kickoff, str) or not kickoff.strip():
            raise ValueError("fixture.date must be a non-empty ISO datetime string")

        fixture_id = fixture.get("id")
        home_id = home.get("id")
        away_id = away.get("id")
        competition_id = league.get("id")
        if any(value is None for value in (fixture_id, home_id, away_id, competition_id)):
            raise ValueError("fixture and team/league identifiers are required")

        return Fixture(
            fixture_id=f"api-football:{fixture_id}",
            home_team=self._text(home, "name"),
            away_team=self._text(away, "name"),
            competition_id=int(competition_id),
            competition_name=self._text(league, "name"),
            country=self._text(league, "country"),
            kickoff_at=datetime.fromisoformat(kickoff.replace("Z", "+00:00")),
            competition_type=str(league.get("type") or "league"),
            season=int(league["season"]) if league.get("season") is not None else None,
            status=str(fixture.get("status", {}).get("short", "scheduled")),
            provider="api-football",
            provider_fixture_id=str(fixture_id),
        )

    @staticmethod
    def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        nested = value.get(key)
        if not isinstance(nested, Mapping):
            raise ValueError(f"{key} must be an object")
        return nested

    @staticmethod
    def _text(value: Mapping[str, Any], key: str) -> str:
        text = value.get(key)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return text
