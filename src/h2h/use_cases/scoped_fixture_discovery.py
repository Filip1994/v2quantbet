"""Application service for discovering fixtures inside the Phase I universe."""

from datetime import datetime

from h2h.domain.competition_scope import CompetitionMetadata, classify_phase_i
from h2h.domain.fixture import Fixture
from h2h.use_cases.fixture_discovery import FixtureDiscovery


class ScopedFixtureDiscovery:
    """Discover provider-neutral fixtures and apply the Phase I scope policy."""

    def __init__(self, discovery: FixtureDiscovery) -> None:
        self._discovery = discovery

    @property
    def has_pending(self) -> bool:
        return bool(getattr(self._discovery, "has_pending", False))

    def discover(self, start_at: datetime, end_at: datetime) -> tuple[Fixture, ...]:
        """Return only fixtures eligible for the configured Phase I universe."""
        if start_at >= end_at:
            raise ValueError("start_at must be earlier than end_at")

        eligible: list[Fixture] = []
        for fixture in self._discovery.discover(start_at, end_at):
            decision = classify_phase_i(
                CompetitionMetadata(
                    country=fixture.country,
                    name=fixture.competition_name,
                    type=fixture.competition_type,
                    level=None,
                    home_team=fixture.home_team,
                    away_team=fixture.away_team,
                )
            )
            if decision.eligible:
                eligible.append(fixture)
        return tuple(eligible)
