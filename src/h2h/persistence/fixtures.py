"""Persistence contract for durable fixture identity and observations."""

from datetime import datetime
from typing import Protocol

from h2h.domain.fixture import Fixture
from h2h.domain.fixture_record import PersistedFixture


class FixturePersistenceConflictError(ValueError):
    """A durable fixture identity or observation was reused inconsistently."""


class FixtureRepository(Protocol):
    def record_discovery(
        self, fixture: Fixture, *, observed_at: datetime
    ) -> PersistedFixture: ...

    def get(self, fixture_id: str) -> PersistedFixture | None: ...

    def get_observation(self, fixture_observation_id: str) -> PersistedFixture | None: ...
