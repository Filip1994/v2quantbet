"""Canonical odds observations for the supported QuantBet markets."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


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

    def __post_init__(self) -> None:
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
        if self.odd <= 1.0:
            raise ValueError("odd must be greater than 1.0")

        valid_selections = {
            Market.OU_25: {Selection.OVER, Selection.UNDER},
            Market.BTTS: {Selection.YES, Selection.NO},
        }
        if self.market not in valid_selections:
            raise ValueError(f"unsupported market: {self.market!r}")
        if self.selection not in valid_selections[self.market]:
            raise ValueError(
                f"selection {self.selection!r} is invalid for market {self.market!r}"
            )
