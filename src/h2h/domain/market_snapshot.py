"""Validated market snapshots built from canonical quote observations."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from .odds import CanonicalQuote, Market, Selection
from .quote_validation import validate_quotes


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """A complete two-sided snapshot for one fixture, bookmaker, and market."""

    fixture_id: str
    bookmaker_id: int
    market: Market
    observed_at: datetime
    quotes: tuple[CanonicalQuote, ...]

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id must not be empty")
        if self.bookmaker_id <= 0:
            raise ValueError("bookmaker_id must be positive")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime")

        validate_quotes(self.quotes)

        for quote in self.quotes:
            if quote.fixture_id != self.fixture_id:
                raise ValueError("all quotes must belong to the same fixture")
            if quote.bookmaker_id != self.bookmaker_id:
                raise ValueError("all quotes must belong to the same bookmaker")
            if quote.market != self.market:
                raise ValueError("all quotes must belong to the same market")
            if quote.observed_at != self.observed_at:
                raise ValueError("all quotes must have the snapshot timestamp")

    @classmethod
    def from_quotes(cls, quotes: Iterable[CanonicalQuote]) -> "MarketSnapshot":
        """Build a snapshot by deriving its shared context from canonical quotes."""
        normalized = tuple(quotes)
        if not normalized:
            raise ValueError("quotes must not be empty")

        first = normalized[0]
        return cls(
            fixture_id=first.fixture_id,
            bookmaker_id=first.bookmaker_id,
            market=first.market,
            observed_at=first.observed_at,
            quotes=normalized,
        )

    def quote_for(self, selection: Selection) -> CanonicalQuote:
        """Return the quote for a selection in this snapshot."""
        for quote in self.quotes:
            if quote.selection == selection:
                return quote
        raise KeyError(selection)
