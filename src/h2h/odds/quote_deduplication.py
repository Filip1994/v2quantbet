"""Explicit duplicate and conflict handling for canonical quote observations."""

from collections.abc import Iterable

from h2h.domain.odds import CanonicalQuote


class QuoteConflictError(ValueError):
    """Raised when one quote identity contains conflicting observations."""


def deduplicate_quotes(quotes: Iterable[CanonicalQuote]) -> tuple[CanonicalQuote, ...]:
    """Return idempotently deduplicated quotes, rejecting conflicting identities.

    Exact repeated observations are collapsed. Two observations with the same
    canonical identity but different data are rejected instead of overwritten.
    The first-seen order is preserved.
    """
    unique: dict[tuple, CanonicalQuote] = {}
    for quote in quotes:
        existing = unique.get(quote.identity)
        if existing is None:
            unique[quote.identity] = quote
            continue
        if existing != quote:
            raise QuoteConflictError(
                f"conflicting observations for quote identity {quote.identity!r}"
            )
    return tuple(unique.values())
