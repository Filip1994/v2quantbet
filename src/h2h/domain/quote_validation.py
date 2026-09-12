"""Validation helpers for canonical quote collections."""

from collections.abc import Iterable

from .odds import CanonicalQuote, Market, Selection


def validate_quotes(quotes: Iterable[CanonicalQuote]) -> tuple[CanonicalQuote, ...]:
    """Validate and normalize quotes before constructing a market snapshot.

    The returned tuple contains exactly one quote for each selection of one
    supported market, with a shared fixture, bookmaker, and observation time.
    """
    normalized = tuple(quotes)
    if not normalized:
        raise ValueError("quotes must not be empty")
    if not all(isinstance(quote, CanonicalQuote) for quote in normalized):
        raise TypeError("quotes must contain only CanonicalQuote instances")

    first = normalized[0]
    expected = {
        Market.OU_25: {Selection.OVER, Selection.UNDER},
        Market.BTTS: {Selection.YES, Selection.NO},
    }[first.market]
    selections = {quote.selection for quote in normalized}

    if len(normalized) != len(expected) or selections != expected:
        raise ValueError(
            f"quotes must contain exactly one selection per market in {expected!r}"
        )

    for quote in normalized[1:]:
        if quote.fixture_id != first.fixture_id:
            raise ValueError("all quotes must belong to the same fixture")
        if quote.bookmaker_id != first.bookmaker_id:
            raise ValueError("all quotes must belong to the same bookmaker")
        if quote.market != first.market:
            raise ValueError("all quotes must belong to the same market")
        if quote.observed_at != first.observed_at:
            raise ValueError("all quotes must have the same observation timestamp")

    return normalized
