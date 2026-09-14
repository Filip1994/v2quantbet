"""Canonical fixture representation independent of any data provider."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Fixture:
    """One scheduled football fixture in the canonical domain model."""

    fixture_id: str
    home_team: str
    away_team: str
    competition_id: int
    competition_name: str
    country: str
    kickoff_at: datetime
    competition_type: str = "league"
    season: int | None = None
    status: str = "scheduled"
    provider: str = "unknown"
    provider_fixture_id: str | None = None

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id must not be empty")
        if not self.home_team.strip() or not self.away_team.strip():
            raise ValueError("home_team and away_team must not be empty")
        if self.competition_id <= 0:
            raise ValueError("competition_id must be positive")
        if not self.competition_name.strip() or not self.country.strip():
            raise ValueError("competition_name and country must not be empty")
        if not self.competition_type.strip():
            raise ValueError("competition_type must not be empty")
        if not isinstance(self.kickoff_at, datetime):
            raise TypeError("kickoff_at must be a datetime")
        if not self.provider.strip():
            raise ValueError("provider must not be empty")
