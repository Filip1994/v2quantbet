"""Record scoped fixture discovery as durable identity and observations."""

from collections.abc import Callable
from datetime import UTC, datetime

from h2h.domain.fixture_record import PersistedFixture
from h2h.persistence.fixtures import FixtureRepository
from h2h.use_cases.fixture_discovery import FixtureDiscovery


class DurableFixtureDiscovery:
    def __init__(
        self,
        discovery: FixtureDiscovery,
        fixtures: FixtureRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._discovery = discovery
        self._fixtures = fixtures
        self._clock = clock

    def discover(self, start_at: datetime, end_at: datetime) -> tuple[PersistedFixture, ...]:
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        observed_at = observed_at.astimezone(UTC)
        return tuple(
            self._fixtures.record_discovery(fixture, observed_at=observed_at)
            for fixture in self._discovery.discover(start_at, end_at)
        )
