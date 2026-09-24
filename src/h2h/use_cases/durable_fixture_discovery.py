"""Record scoped fixture discovery as bounded durable observations."""

import logging
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

from h2h.domain.fixture import Fixture
from h2h.domain.fixture_record import PersistedFixture
from h2h.persistence.fixtures import FixturePersistenceConflictError, FixtureRepository
from h2h.use_cases.fixture_discovery import FixtureDiscovery


LOGGER = logging.getLogger("quantbet.discovery")


class DurableFixtureDiscovery:
    def __init__(
        self,
        discovery: FixtureDiscovery,
        fixtures: FixtureRepository,
        *,
        clock: Callable[[], datetime],
        max_per_call: int = 10,
    ) -> None:
        if isinstance(max_per_call, bool) or not isinstance(max_per_call, int):
            raise TypeError("max_per_call must be an integer")
        if max_per_call <= 0:
            raise ValueError("max_per_call must be positive")
        self._discovery = discovery
        self._fixtures = fixtures
        self._clock = clock
        self._max_per_call = max_per_call
        self._pending: deque[Fixture] = deque()

    @property
    def has_pending(self) -> bool:
        return bool(self._pending) or bool(getattr(self._discovery, "has_pending", False))

    def discover(self, start_at: datetime, end_at: datetime) -> tuple[PersistedFixture, ...]:
        if not self._pending:
            self._pending.extend(self._discovery.discover(start_at, end_at))
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        observed_at = observed_at.astimezone(UTC)
        persisted: list[PersistedFixture] = []
        attempts = 0
        while self._pending and attempts < self._max_per_call:
            fixture = self._pending[0]
            attempts += 1
            try:
                durable = self._fixtures.record_discovery(fixture, observed_at=observed_at)
            except FixturePersistenceConflictError:
                # Provider-side identity drift must remain fail-closed for this fixture,
                # but one poisoned discovery item must not terminate the whole scheduler.
                # Consume the conflicting item from the in-memory batch, emit enough
                # identity context for diagnosis, and continue with the next fixture.
                LOGGER.exception(
                    "fixture discovery identity conflict quarantined",
                    extra={
                        "fixture_id": fixture.fixture_id,
                        "provider": fixture.provider,
                        "provider_fixture_id": fixture.provider_fixture_id,
                        "league_id": fixture.competition_id,
                        "season": fixture.season,
                        "provider_home_team_id": fixture.provider_home_team_id,
                        "provider_away_team_id": fixture.provider_away_team_id,
                    },
                )
                self._pending.popleft()
                continue
            persisted.append(durable)
            self._pending.popleft()
        return tuple(persisted)
