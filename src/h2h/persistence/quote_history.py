"""Persistence contract and in-memory implementation for quote history."""

from collections.abc import Iterable
from typing import Protocol

from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot


class QuoteHistoryRepository(Protocol):
    """Provider-neutral storage boundary for immutable quote observations."""

    def ensure_series(self, series: QuoteSeries) -> None:
        """Create a series or reject a conflicting definition."""
        ...

    def find_series(
        self,
        *,
        fixture_id: str,
        bookmaker_id: int,
        market: str,
        selection: str,
    ) -> QuoteSeries | None:
        """Find a series by its stable natural identity."""
        ...

    def series_for_fixture(self, fixture_id: str) -> tuple[QuoteSeries, ...]:
        """Return registered quote series for one fixture in insertion order."""
        ...

    def append_snapshots(self, snapshots: Iterable[QuoteSnapshot]) -> None:
        """Append snapshots idempotently, rejecting conflicts and unknown series."""
        ...

    def snapshots_for_series(self, series_id: str) -> tuple[QuoteSnapshot, ...]:
        """Return snapshots for a series in insertion order."""
        ...

    def get_snapshot(self, snapshot_id: str) -> QuoteSnapshot | None:
        """Return one snapshot by ID, if present."""
        ...


class QuoteHistoryConflictError(ValueError):
    """Raised when an immutable series or snapshot identity is reused inconsistently."""


class InMemoryQuoteHistoryRepository:
    """Deterministic in-memory implementation for tests and local composition."""

    def __init__(self) -> None:
        self._series: dict[str, QuoteSeries] = {}
        self._series_order: list[str] = []
        self._snapshots: dict[str, QuoteSnapshot] = {}
        self._snapshot_order: list[str] = []

    def ensure_series(self, series: QuoteSeries) -> None:
        existing = self._series.get(series.series_id)
        if existing is not None:
            if existing != series:
                raise QuoteHistoryConflictError(
                    f"conflicting definition for series ID {series.series_id!r}"
                )
            return
        natural_match = self.find_series(
            fixture_id=series.fixture_id,
            bookmaker_id=series.bookmaker_id,
            market=series.market.value,
            selection=series.selection.value,
        )
        if natural_match is not None and natural_match != series:
            raise QuoteHistoryConflictError(
                "conflicting definition for quote series natural identity"
            )
        self._series[series.series_id] = series
        self._series_order.append(series.series_id)

    def find_series(
        self,
        *,
        fixture_id: str,
        bookmaker_id: int,
        market: str,
        selection: str,
    ) -> QuoteSeries | None:
        return next(
            (
                series
                for series in self._series.values()
                if (
                    series.fixture_id == fixture_id
                    and series.bookmaker_id == bookmaker_id
                    and series.market.value == market
                    and series.selection.value == selection
                )
            ),
            None,
        )

    def series_for_fixture(self, fixture_id: str) -> tuple[QuoteSeries, ...]:
        return tuple(
            self._series[series_id]
            for series_id in self._series_order
            if self._series[series_id].fixture_id == fixture_id
        )

    @staticmethod
    def _snapshot_natural_key(snapshot: QuoteSnapshot) -> tuple[object, ...]:
        return (
            snapshot.series_id,
            snapshot.observed_at,
            snapshot.source,
        )

    def append_snapshots(self, snapshots: Iterable[QuoteSnapshot]) -> None:
        incoming = tuple(snapshots)
        pending = dict(self._snapshots)
        pending_order = list(self._snapshot_order)
        natural_keys: dict[tuple[object, ...], QuoteSnapshot] = {
            self._snapshot_natural_key(snapshot): snapshot
            for snapshot in pending.values()
        }
        for snapshot in incoming:
            if snapshot.series_id not in self._series:
                raise QuoteHistoryConflictError(
                    f"unknown series ID {snapshot.series_id!r}"
                )
            existing = pending.get(snapshot.snapshot_id)
            if existing is not None:
                if (
                    self._snapshot_natural_key(existing) != self._snapshot_natural_key(snapshot)
                    or existing.odd != snapshot.odd
                ):
                    raise QuoteHistoryConflictError(
                        f"conflicting observation for snapshot ID {snapshot.snapshot_id!r}"
                    )
                continue
            natural_key = self._snapshot_natural_key(snapshot)
            natural_match = natural_keys.get(natural_key)
            if natural_match is not None:
                if natural_match.odd != snapshot.odd:
                    raise QuoteHistoryConflictError(
                        "conflicting observation for snapshot natural identity"
                    )
                continue
            pending[snapshot.snapshot_id] = snapshot
            pending_order.append(snapshot.snapshot_id)
            natural_keys[natural_key] = snapshot
        self._snapshots = pending
        self._snapshot_order = pending_order

    def snapshots_for_series(self, series_id: str) -> tuple[QuoteSnapshot, ...]:
        return tuple(
            self._snapshots[snapshot_id]
            for snapshot_id in self._snapshot_order
            if self._snapshots[snapshot_id].series_id == series_id
        )

    def get_snapshot(self, snapshot_id: str) -> QuoteSnapshot | None:
        return self._snapshots.get(snapshot_id)
