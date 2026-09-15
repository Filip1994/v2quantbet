"""Explicit duplicate and conflict handling for canonical quote observations."""

from collections.abc import Iterable

from h2h.domain.odds import CanonicalQuote


class QuoteConflictError(ValueError):
    """Raised when one observation identity contains conflicting data."""


def deduplicate_quotes(quotes: Iterable[CanonicalQuote]) -> tuple[CanonicalQuote, ...]:
    """Deduplicate replayed observations while preserving quote history.

    Repeated observations with the same series, provider timestamp and source
    are collapsed. A changed odd for that same observation identity is
    rejected rather than silently overwritten. Observations at different
    provider timestamps remain distinct historical records.
    """
    unique: dict[tuple, CanonicalQuote] = {}
    for quote in quotes:
        key = quote.observation_identity
        existing = unique.get(key)
        if existing is None:
            unique[key] = quote
            continue
        if existing != quote:
            raise QuoteConflictError(
                f"conflicting observations for quote identity {key!r}"
            )
    return tuple(unique.values())
