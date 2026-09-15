"""Translate API-Football fixture payloads into canonical fixtures."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from h2h.domain.fixture import Fixture


class ApiFootballFixtureAdapter:
    """Convert one API-Football fixture object into a canonical ``Fixture``."""

    def adapt(self, payload: Mapping[str, Any]) -> Fixture:
        """Translate a provider fixture payload without leaking provider fields."""
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be an object")

        fixture = self._mapping(payload, "fixture")
        teams = self._mapping(payload, "teams")
        home = self._mapping(teams, "home")
        away = self._mapping(teams, "away")
        league = self._mapping(payload, "league")

        fixture_id = self._positive_int(fixture.get("id"), "fixture.id")
        home_team_id = self._positive_int(home.get("id"), "teams.home.id")
        away_team_id = self._positive_int(away.get("id"), "teams.away.id")
        competition_id = self._positive_int(league.get("id"), "league.id")

        return Fixture(
            fixture_id=f"api-football:{fixture_id}",
            home_team=self._text(home, "name"),
            away_team=self._text(away, "name"),
            competition_id=competition_id,
            competition_name=self._text(league, "name"),
            country=self._text(league, "country"),
            kickoff_at=self._kickoff(fixture.get("date")),
            competition_type=self._competition_type(league),
            season=self._optional_int(league.get("season"), "league.season"),
            status=self._status(fixture),
            provider="api-football",
            provider_fixture_id=str(fixture_id),
            provider_home_team_id=home_team_id,
            provider_away_team_id=away_team_id,
        )

    @staticmethod
    def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        nested = value.get(key)
        if not isinstance(nested, Mapping):
            raise TypeError(f"{key} must be an object")
        return nested

    @staticmethod
    def _text(value: Mapping[str, Any], key: str) -> str:
        text = value.get(key)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return text

    @staticmethod
    def _positive_int(value: Any, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field} must be a positive integer")
        return value

    @classmethod
    def _optional_int(cls, value: Any, field: str) -> int | None:
        if value is None:
            return None
        return cls._positive_int(value, field)

    @staticmethod
    def _kickoff(value: Any) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("fixture.date must be a non-empty ISO datetime string")
        try:
            kickoff = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("fixture.date must be a valid ISO datetime string") from exc
        if kickoff.tzinfo is None or kickoff.utcoffset() is None:
            raise ValueError("fixture.date must include a timezone offset")
        return kickoff

    @staticmethod
    def _competition_type(league: Mapping[str, Any]) -> str:
        value = league.get("type")
        if value is None:
            return "league"
        if not isinstance(value, str) or not value.strip():
            raise ValueError("league.type must be a non-empty string")
        return value

    @staticmethod
    def _status(fixture: Mapping[str, Any]) -> str:
        value = fixture.get("status")
        if value is None:
            return "scheduled"
        if not isinstance(value, Mapping):
            raise TypeError("fixture.status must be an object")
        short = value.get("short")
        if not isinstance(short, str) or not short.strip():
            raise ValueError("fixture.status.short must be a non-empty string")
        return short
