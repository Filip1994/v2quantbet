"""Provider-neutral fixture discovery contract."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from h2h.domain.fixture import Fixture


class FixtureDiscovery(Protocol):
    """Port implemented by providers capable of discovering fixtures."""

    def discover(self, start_at: datetime, end_at: datetime) -> Sequence[Fixture]:
        """Return fixtures whose scheduled kickoff is within the requested window."""
        ...
