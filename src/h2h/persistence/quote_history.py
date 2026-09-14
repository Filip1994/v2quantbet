"""Persistence contract and in-memory implementation for quote history."""

from collections.abc import Iterable
from typing import Protocol

from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot


class QuoteHistoryRepository(Protocol):
    """Provider-neutral storage boundary for immutable quote observations."""

    def ensure_series(self, series: QuoteSeries) -> None:
        """Create a series or reject a conflicting definition."""
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
    """Raised when an immutable series or snapshot ID is reused inconsistently."""


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
        self._series[series.series_id] = series
        self._series_order.append(series.series_id)

    def series_for_fixture(self, fixture_id: str) -> tuple[QuoteSeries, ...]:
        return tuple(
            self._series[series_id]
            for series_id in self._series_order
            if self._series[series_id].fixture_id == fixture_id
        )

    def append_snapshots(self, snapshots: Iterable[QuoteSnapshot]) -> None:
        incoming = tuple(snapshots)
        pending = dict(self._snapshots)
        pending_order = list(self._snapshot_order)
        for snapshot in incoming:
            if snapshot.series_id not in self._series:
                raise QuoteHistoryConflictError(
                    f"unknown series ID {snapshot.series_id!r}"
                )
            existing = pending.get(snapshot.snapshot_id)
            if existing is None:
                pending[snapshot.snapshot_id] = snapshot
                pending_order.append(snapshot.snapshot_id)
            elif existing != snapshot:
                raise QuoteHistoryConflictError(
                    f"conflicting observation for snapshot ID {snapshot.snapshot_id!r}"
                )
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
