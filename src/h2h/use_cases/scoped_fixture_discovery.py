"""Application service for discovering fixtures inside the Phase I universe."""

from collections.abc import Sequence
from datetime import datetime

from h2h.domain.competition_scope import CompetitionMetadata, classify_phase_i
from h2h.domain.fixture import Fixture
from h2h.use_cases.fixture_discovery import FixtureDiscovery


class ScopedFixtureDiscovery:
    """Discover provider-neutral fixtures and apply the Phase I scope policy."""

    def __init__(self, discovery: FixtureDiscovery) -> None:
        self._discovery = discovery

    def discover(self, start_at: datetime, end_at: datetime) -> tuple[Fixture, ...]:
        """Return only fixtures eligible for the configured Phase I universe."""
        if start_at >= end_at:
            raise ValueError("start_at must be earlier than end_at")

        fixtures = self._discovery.discover(start_at, end_at)
        eligible: list[Fixture] = []
        for fixture in fixtures:
            decision = classify_phase_i(
                CompetitionMetadata(
                    country=fixture.country,
                    name=fixture.competition_name,
                    type=fixture.status,
                    level=None,
                )
            )
            if decision.eligible:
                eligible.append(fixture)
        return tuple(eligible)
