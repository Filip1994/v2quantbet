"""Polling job that refreshes fixture discovery before collecting quote history."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Protocol

from h2h.domain.fixture import Fixture
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.workers.history_quote_polling import HistoricalQuoteSource


class ScopedFixtureDiscoveryPort(Protocol):
    """Discover fixtures eligible for the QuantBet production scope."""

    def discover(self, start_at: datetime, end_at: datetime) -> Sequence[Fixture]:
        """Return eligible fixtures scheduled inside the requested window."""


class DiscoveredHistoryQuotePollingJob:
    """Discover upcoming fixtures and collect quote history for them."""

    def __init__(
        self,
        source: HistoricalQuoteSource,
        ingestion: QuoteHistoryIngestionService,
        discovery: ScopedFixtureDiscoveryPort,
        *,
        clock: Callable[[], datetime] | None = None,
        lookahead: timedelta = timedelta(hours=24),
    ) -> None:
        if lookahead <= timedelta(0):
            raise ValueError("lookahead must be positive")
        self._source = source
        self._ingestion = ingestion
        self._discovery = discovery
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lookahead = lookahead

    def run_once(self) -> int:
        """Discover the current window and persist quotes for all provider fixture IDs."""
        start_at = self._clock()
        if start_at.tzinfo is None or start_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        end_at = start_at + self._lookahead

        total = 0
        seen: set[int] = set()
        for fixture in self._discovery.discover(start_at, end_at):
            provider_fixture_id = fixture.provider_fixture_id
            if provider_fixture_id is None:
                continue
            try:
                fixture_id = int(provider_fixture_id)
            except ValueError:
                continue
            if fixture_id <= 0 or fixture_id in seen:
                continue
            seen.add(fixture_id)
            total += self._ingestion.ingest(
                self._source.fetch_quotes(fixture_id=fixture_id)
            )
        return total
