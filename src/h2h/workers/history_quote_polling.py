"""Polling job that persists immutable historical quote observations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from h2h.domain.odds import CanonicalQuote
from h2h.use_cases.quote_history import QuoteHistoryIngestionService


class HistoricalQuoteSource(Protocol):
    """Fetch currently observed canonical quotes for one fixture."""

    def fetch_quotes(self, *, fixture_id: int) -> tuple[CanonicalQuote, ...]:
        """Return the provider-normalized quotes currently available."""


class HistoryQuotePollingJob:
    """Collect one polling cycle and persist every observation as history."""

    def __init__(
        self,
        source: HistoricalQuoteSource,
        ingestion: QuoteHistoryIngestionService,
        fixture_ids: Iterable[int],
    ) -> None:
        self._source = source
        self._ingestion = ingestion
        self._fixture_ids = tuple(fixture_ids)
        if any(fixture_id <= 0 for fixture_id in self._fixture_ids):
            raise ValueError("fixture_ids must contain positive integers")

    def run_once(self) -> int:
        """Collect all configured fixtures and return the number of snapshots."""
        total = 0
        for fixture_id in self._fixture_ids:
            total += self._ingestion.ingest(
                self._source.fetch_quotes(fixture_id=fixture_id)
            )
        return total
