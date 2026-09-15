"""Canonical odds observations for the supported QuantBet markets."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


class Market(StrEnum):
    """Supported market families."""

    OU_25 = "OU_25"
    BTTS = "BTTS"


class Selection(StrEnum):
    """Possible selections across supported market families."""

    OVER = "OVER"
    UNDER = "UNDER"
    YES = "YES"
    NO = "NO"


@dataclass(frozen=True, slots=True)
class CanonicalQuote:
    """One immutable observation of a bookmaker quote."""

    fixture_id: str
    bookmaker_id: int
    bookmaker_name: str
    market: Market
    selection: Selection
    odd: float
    observed_at: datetime
    source: str

    @property
    def series_identity(self) -> tuple[str, int, Market, Selection]:
        """Return the stable identity of the quote series."""
        return (self.fixture_id, self.bookmaker_id, self.market, self.selection)

    @property
    def identity(self) -> tuple[str, int, Market, Selection]:
        """Backward-compatible alias for the quote-series identity."""
        return self.series_identity

    @property
    def observation_identity(self) -> tuple[str, int, Market, Selection, datetime, str]:
        """Return the identity of one provider observation within a series."""
        return (*self.series_identity, self.observed_at, self.source)

    def __post_init__(self) -> None:
        if not isinstance(self.fixture_id, str):
            raise TypeError("fixture_id must be a string")
        if isinstance(self.bookmaker_id, bool) or not isinstance(self.bookmaker_id, int):
            raise TypeError("bookmaker_id must be an integer")
        if not isinstance(self.bookmaker_name, str):
            raise TypeError("bookmaker_name must be a string")
        if not isinstance(self.market, Market):
            raise TypeError("market must be a Market")
        if not isinstance(self.selection, Selection):
            raise TypeError("selection must be a Selection")
        if not isinstance(self.source, str):
            raise TypeError("source must be a string")

        if not self.fixture_id.strip():
            raise ValueError("fixture_id must not be empty")
        if self.bookmaker_id <= 0:
            raise ValueError("bookmaker_id must be positive")
        if not self.bookmaker_name.strip():
            raise ValueError("bookmaker_name must not be empty")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if not isfinite(self.odd) or self.odd <= 1.0:
            raise ValueError("odd must be finite and greater than 1.0")

        valid_selections = {
            Market.OU_25: {Selection.OVER, Selection.UNDER},
            Market.BTTS: {Selection.YES, Selection.NO},
        }
        if self.selection not in valid_selections[self.market]:
            raise ValueError(
                f"selection {self.selection!r} is invalid for market {self.market!r}"
            )
