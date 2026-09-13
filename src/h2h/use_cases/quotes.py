"""Application service for persisting and reading canonical quote observations."""

from collections.abc import Iterable

from h2h.domain.odds import CanonicalQuote
from h2h.persistence import QuoteRepository


class QuoteIngestionService:
    """Coordinate quote writes and fixture-scoped reads without provider coupling."""

    def __init__(self, repository: QuoteRepository) -> None:
        self._repository = repository

    def ingest(self, quotes: Iterable[CanonicalQuote]) -> None:
        """Persist canonical quotes using the repository's atomic semantics."""
        self._repository.save(quotes)

    def read_fixture(self, fixture_id: str) -> tuple[CanonicalQuote, ...]:
        """Read all persisted quotes for one fixture."""
        return self._repository.for_fixture(fixture_id)

    def read_all(self) -> tuple[CanonicalQuote, ...]:
        """Read all persisted quotes in repository order."""
        return self._repository.all()
