"""Polling job that persists immutable historical quote observations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from h2h.domain.fixture_identity import ResolvedFixtureIdentity
from h2h.domain.odds import CanonicalQuote
from h2h.use_cases.quote_history import QuoteHistoryIngestionService


class HistoricalQuoteSource(Protocol):
    """Fetch currently observed canonical quotes for one fixture."""

    def fetch_quotes(
        self,
        *,
        fixture_identity: ResolvedFixtureIdentity,
    ) -> tuple[CanonicalQuote, ...]:
        """Return the provider-normalized quotes currently available."""


class HistoryQuotePollingJob:
    """Collect one polling cycle and persist every observation as history."""

    def __init__(
        self,
        source: HistoricalQuoteSource,
        ingestion: QuoteHistoryIngestionService,
        fixture_identities: Iterable[ResolvedFixtureIdentity],
    ) -> None:
        self._source = source
        self._ingestion = ingestion
        self._fixture_identities = tuple(fixture_identities)
        if not all(
            isinstance(identity, ResolvedFixtureIdentity)
            for identity in self._fixture_identities
        ):
            raise TypeError(
                "fixture_identities must contain ResolvedFixtureIdentity instances"
            )

    def run_once(self) -> int:
        """Collect all configured fixtures and return the number of snapshots."""
        total = 0
        for fixture_identity in self._fixture_identities:
            total += self._ingestion.ingest(
                self._source.fetch_quotes(fixture_identity=fixture_identity)
            )
        return total
