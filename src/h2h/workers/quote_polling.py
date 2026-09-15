"""Provider-neutral polling job for pre-match quote ingestion."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from h2h.domain.fixture_identity import ResolvedFixtureIdentity
from h2h.domain.odds import CanonicalQuote
from h2h.use_cases import QuoteIngestionService


class QuoteSource(Protocol):
    """Fetch normalized quotes for a fixture."""

    def fetch_quotes(
        self,
        *,
        fixture_identity: ResolvedFixtureIdentity,
    ) -> tuple[CanonicalQuote, ...]:
        """Return the currently observed quotes for one fixture."""


class QuotePollingJob:
    """Fetch and persist one polling cycle for a fixed fixture set.

    Fixture discovery is deliberately outside this class. A later scheduler can
    replace the fixture list without coupling the ingestion boundary to a
    particular provider or database.
    """

    def __init__(
        self,
        source: QuoteSource,
        ingestion: QuoteIngestionService,
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
        """Ingest one cycle and return the number of quotes written."""
        total = 0
        for fixture_identity in self._fixture_identities:
            quotes = self._source.fetch_quotes(fixture_identity=fixture_identity)
            self._ingestion.ingest(quotes)
            total += len(quotes)
        return total
