"""Durable fixture identity and append-only discovery observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be expressed in UTC")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class FixtureIdentityRecord:
    fixture_id: str
    provider: str
    provider_fixture_id: str
    league_id: int
    season: int
    provider_home_team_id: int
    provider_away_team_id: int
    created_at: datetime

    def __post_init__(self) -> None:
        for name in ("fixture_id", "provider", "provider_fixture_id"):
            _text(getattr(self, name), name)
        for name in (
            "league_id",
            "season",
            "provider_home_team_id",
            "provider_away_team_id",
        ):
            _positive_int(getattr(self, name), name)
        if self.provider_home_team_id == self.provider_away_team_id:
            raise ValueError("provider home and away team IDs must be different")
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))


@dataclass(frozen=True, slots=True)
class FixtureObservation:
    fixture_observation_id: str
    fixture_id: str
    home_team: str
    away_team: str
    competition_name: str
    country: str
    competition_type: str
    kickoff_at: datetime
    provider_status: str
    source: str
    observed_at: datetime
    persisted_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "fixture_observation_id",
            "fixture_id",
            "home_team",
            "away_team",
            "competition_name",
            "country",
            "competition_type",
            "provider_status",
            "source",
        ):
            _text(getattr(self, name), name)
        for name in ("kickoff_at", "observed_at", "persisted_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class PersistedFixture:
    identity: FixtureIdentityRecord
    observation: FixtureObservation

    def __post_init__(self) -> None:
        if self.identity.fixture_id != self.observation.fixture_id:
            raise ValueError("fixture identity and observation must match")
