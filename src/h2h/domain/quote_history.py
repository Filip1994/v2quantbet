"""Immutable domain objects for historical pre-match quote observations."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from .odds import Market, Selection


def _require_non_empty_text(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class QuoteSeries:
    """Stable identity for one fixture/bookmaker/market/selection series."""

    series_id: str
    fixture_id: str
    bookmaker_id: int
    market: Market
    selection: Selection
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.series_id, "series_id")
        _require_non_empty_text(self.fixture_id, "fixture_id")
        if isinstance(self.bookmaker_id, bool) or not isinstance(self.bookmaker_id, int):
            raise TypeError("bookmaker_id must be an int")
        if self.bookmaker_id <= 0:
            raise ValueError("bookmaker_id must be positive")
        if not isinstance(self.market, Market):
            raise TypeError("market must be a Market")
        if not isinstance(self.selection, Selection):
            raise TypeError("selection must be a Selection")
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    """One immutable, timestamped pre-match observation in a quote series."""

    snapshot_id: str
    series_id: str
    odd: float
    observed_at: datetime
    captured_at: datetime
    source: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.snapshot_id, "snapshot_id")
        _require_non_empty_text(self.series_id, "series_id")
        if isinstance(self.odd, bool) or not isinstance(self.odd, (int, float)):
            raise TypeError("odd must be a number")
        if not isfinite(self.odd) or self.odd <= 1.0:
            raise ValueError("odd must be finite and greater than 1.0")
        _require_non_empty_text(self.source, "source")
        _require_aware(self.observed_at, "observed_at")
        _require_aware(self.captured_at, "captured_at")
