"""Persistence contract and in-memory implementation for canonical quotes."""

from collections.abc import Iterable
from typing import Protocol

from h2h.domain.odds import CanonicalQuote
from h2h.odds.quote_deduplication import QuoteConflictError


class QuoteRepository(Protocol):
    """Provider-neutral storage boundary for canonical quote observations."""

    def save(self, quotes: Iterable[CanonicalQuote]) -> None:
        """Persist quotes idempotently, rejecting conflicting identities."""
        ...

    def all(self) -> tuple[CanonicalQuote, ...]:
        """Return all stored quotes in insertion order."""
        ...

    def for_fixture(self, fixture_id: str) -> tuple[CanonicalQuote, ...]:
        """Return stored quotes belonging to one fixture."""
        ...


class InMemoryQuoteRepository:
    """Small deterministic repository for tests and local composition.

    The implementation stores only canonical domain objects. A save operation
    is atomic: conflicts are detected before the internal store is changed.
    """

    def __init__(self) -> None:
        self._quotes: dict[tuple[str, int, object, object], CanonicalQuote] = {}

    def save(self, quotes: Iterable[CanonicalQuote]) -> None:
        """Persist quotes, ignoring exact duplicates and rejecting conflicts."""
        incoming = tuple(quotes)
        pending = dict(self._quotes)
        for quote in incoming:
            existing = pending.get(quote.identity)
            if existing is None:
                pending[quote.identity] = quote
            elif existing != quote:
                raise QuoteConflictError(
                    f"conflicting observations for quote identity {quote.identity!r}"
                )
        self._quotes = pending

    def all(self) -> tuple[CanonicalQuote, ...]:
        """Return all stored quotes in insertion order."""
        return tuple(self._quotes.values())

    def for_fixture(self, fixture_id: str) -> tuple[CanonicalQuote, ...]:
        """Return quotes for ``fixture_id`` in insertion order."""
        return tuple(
            quote for quote in self._quotes.values() if quote.fixture_id == fixture_id
        )
