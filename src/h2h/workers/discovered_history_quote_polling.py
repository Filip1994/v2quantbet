"""Polling job that refreshes fixture discovery before collecting quote history."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Protocol

from h2h.domain.fixture import Fixture
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.workers.history_quote_polling import HistoricalQuoteSource
from h2h.workers.quote_refresh_scheduler import QuoteRefreshScheduler

LOGGER = logging.getLogger(__name__)


class ScopedFixtureDiscoveryPort(Protocol):
    """Discover fixtures eligible for the QuantBet production scope."""

    def discover(self, start_at: datetime, end_at: datetime) -> Sequence[Fixture]:
        """Return eligible fixtures scheduled inside the requested window."""


class DiscoveredHistoryQuotePollingJob:
    """Discover upcoming fixtures and collect quotes on kickoff-aware cadence."""

    def __init__(
        self,
        source: HistoricalQuoteSource,
        ingestion: QuoteHistoryIngestionService,
        discovery: ScopedFixtureDiscoveryPort,
        *,
        clock: Callable[[], datetime] | None = None,
        lookahead: timedelta = timedelta(hours=72),
    ) -> None:
        if lookahead <= timedelta(0):
            raise ValueError("lookahead must be positive")
        self._source = source
        self._ingestion = ingestion
        self._discovery = discovery
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lookahead = lookahead
        self._scheduler = QuoteRefreshScheduler()
        self._known_kickoffs: dict[int, datetime] = {}

    def run_once(self) -> int:
        """Discover fixtures and refresh only new or currently due fixtures."""
        start_at = self._clock()
        if start_at.tzinfo is None or start_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        end_at = start_at + self._lookahead

        try:
            fixtures = self._discovery.discover(start_at, end_at)
        except Exception:
            LOGGER.exception(
                "Fixture discovery failed for window %s to %s",
                start_at,
                end_at,
            )
            return 0

        due_ids = set(self._scheduler.due_fixture_ids(now=start_at))
        candidates: dict[int, Fixture] = {}
        for fixture in fixtures:
            provider_fixture_id = fixture.provider_fixture_id
            if provider_fixture_id is None:
                continue
            try:
                fixture_id = int(provider_fixture_id)
            except (TypeError, ValueError):
                continue
            if fixture_id <= 0 or fixture_id in candidates:
                continue
            if fixture.kickoff_at.tzinfo is None or fixture.kickoff_at.utcoffset() is None:
                LOGGER.warning("Ignoring fixture_id=%s with naive kickoff", fixture_id)
                continue

            previous_kickoff = self._known_kickoffs.get(fixture_id)
            if previous_kickoff != fixture.kickoff_at:
                self._known_kickoffs[fixture_id] = fixture.kickoff_at
                scheduled = self._scheduler.register(
                    fixture_id=fixture_id,
                    kickoff_at=fixture.kickoff_at,
                    now=start_at,
                )
                if scheduled is not None:
                    candidates[fixture_id] = fixture
            elif fixture_id in due_ids:
                candidates[fixture_id] = fixture

        total = 0
        for fixture_id, fixture in candidates.items():
            try:
                total += self._ingestion.ingest(
                    self._source.fetch_quotes(fixture_id=fixture_id)
                )
            except Exception:
                LOGGER.exception(
                    "Failed to collect or ingest quote history for fixture_id=%s",
                    fixture_id,
                )
                # A failed first refresh must remain retryable on the next cycle.
                # Do not leave a future scheduled slot or a known-kickoff marker
                # that would suppress the retry.
                self._known_kickoffs.pop(fixture_id, None)
                self._scheduler.remove(fixture_id)
                continue
            self._scheduler.mark_refreshed(fixture_id=fixture_id, now=start_at)
        return total
