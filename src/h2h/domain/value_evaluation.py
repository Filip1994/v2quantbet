"""Immutable two-sided market observations and value evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from .odds import Market, Selection


PROPORTIONAL_TWO_WAY_V1 = "PROPORTIONAL_TWO_WAY_V1"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be expressed in UTC")
    return value.astimezone(UTC)


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class PersistedQuoteObservation:
    series_id: str
    snapshot_id: str
    fixture_id: str
    bookmaker_id: int
    bookmaker_key: str
    market: Market
    selection: Selection
    odd: float
    observed_at: datetime
    captured_at: datetime
    source: str

    def __post_init__(self) -> None:
        for name in ("series_id", "snapshot_id", "fixture_id", "bookmaker_key", "source"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        if isinstance(self.bookmaker_id, bool) or not isinstance(self.bookmaker_id, int):
            raise TypeError("bookmaker_id must be an integer")
        if self.bookmaker_id <= 0:
            raise ValueError("bookmaker_id must be positive")
        if not isinstance(self.market, Market) or not isinstance(self.selection, Selection):
            raise TypeError("market and selection must use canonical enums")
        odd = _finite(self.odd, "odd")
        if odd <= 1.0:
            raise ValueError("odd must be greater than 1")
        object.__setattr__(self, "odd", odd)
        for name in ("observed_at", "captured_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class PersistedMarketObservation:
    quotes: tuple[PersistedQuoteObservation, PersistedQuoteObservation]

    def __post_init__(self) -> None:
        quotes = tuple(self.quotes)
        if len(quotes) != 2 or not all(isinstance(q, PersistedQuoteObservation) for q in quotes):
            raise ValueError("market observation must contain exactly two persisted quotes")
        first, second = quotes
        shared = lambda q: (
            q.fixture_id,
            q.bookmaker_id,
            q.bookmaker_key,
            q.market,
            q.observed_at,
            q.source,
        )
        if shared(first) != shared(second):
            raise ValueError("market quotes must share exact observation context")
        expected = {
            Market.OU_25: {Selection.OVER, Selection.UNDER},
            Market.BTTS: {Selection.YES, Selection.NO},
        }[first.market]
        if {first.selection, second.selection} != expected:
            raise ValueError("market observation must contain complementary selections")
        if first.series_id == second.series_id or first.snapshot_id == second.snapshot_id:
            raise ValueError("market quote identities must be distinct")
        object.__setattr__(self, "quotes", quotes)

    def selected(
        self, snapshot_id: str
    ) -> tuple[PersistedQuoteObservation, PersistedQuoteObservation]:
        matches = [quote for quote in self.quotes if quote.snapshot_id == snapshot_id]
        if len(matches) != 1:
            raise KeyError(snapshot_id)
        selected = matches[0]
        companion = self.quotes[1] if selected is self.quotes[0] else self.quotes[0]
        return selected, companion


@dataclass(frozen=True, slots=True)
class ValueEvaluation:
    evaluation_id: str
    fixture_id: str
    prediction_id: str
    model_version_id: str
    selected_series_id: str
    companion_series_id: str
    selected_snapshot_id: str
    companion_snapshot_id: str
    bookmaker_id: int
    bookmaker_key: str
    market: Market
    selected_selection: Selection
    companion_selection: Selection
    quote_observed_at: datetime
    source: str
    selected_captured_at: datetime
    companion_captured_at: datetime
    selected_odd: float
    companion_odd: float
    selected_raw_implied_probability: float
    companion_raw_implied_probability: float
    overround: float
    devig_method_version: str
    selected_devig_probability: float
    model_probability: float
    edge: float
    expected_value: float
    evaluated_at: datetime
    persisted_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "evaluation_id",
            "fixture_id",
            "prediction_id",
            "model_version_id",
            "selected_series_id",
            "companion_series_id",
            "selected_snapshot_id",
            "companion_snapshot_id",
            "bookmaker_key",
            "source",
            "devig_method_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        if self.selected_series_id == self.companion_series_id:
            raise ValueError("selected and companion series must differ")
        if self.selected_snapshot_id == self.companion_snapshot_id:
            raise ValueError("selected and companion snapshots must differ")
        if self.selected_selection == self.companion_selection:
            raise ValueError("selected and companion selections must differ")
        if (
            isinstance(self.bookmaker_id, bool)
            or not isinstance(self.bookmaker_id, int)
            or self.bookmaker_id <= 0
        ):
            raise ValueError("bookmaker_id must be a positive integer")
        for name in (
            "quote_observed_at",
            "selected_captured_at",
            "companion_captured_at",
            "evaluated_at",
            "persisted_at",
        ):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        for name in (
            "selected_odd",
            "companion_odd",
            "selected_raw_implied_probability",
            "companion_raw_implied_probability",
            "overround",
            "selected_devig_probability",
            "model_probability",
            "edge",
            "expected_value",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.selected_odd <= 1.0 or self.companion_odd <= 1.0:
            raise ValueError("odds must be greater than 1")
        for name in (
            "selected_raw_implied_probability",
            "companion_raw_implied_probability",
            "selected_devig_probability",
            "model_probability",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.overround <= 0.0:
            raise ValueError("overround must be positive")
        self.validate_arithmetic()

    def validate_arithmetic(self) -> None:
        values = {
            "selected_raw_implied_probability": 1.0 / self.selected_odd,
            "companion_raw_implied_probability": 1.0 / self.companion_odd,
        }
        values["overround"] = sum(values.values())
        values["selected_devig_probability"] = (
            values["selected_raw_implied_probability"] / values["overround"]
        )
        values["edge"] = self.model_probability - values["selected_devig_probability"]
        values["expected_value"] = self.model_probability * self.selected_odd - 1.0
        for name, expected in values.items():
            if abs(getattr(self, name) - expected) > 1e-12:
                raise ValueError(f"stored {name} contradicts evaluation arithmetic")
