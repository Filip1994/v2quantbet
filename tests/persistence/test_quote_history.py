from datetime import datetime, timezone

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.persistence.quote_history import (
    InMemoryQuoteHistoryRepository,
    QuoteHistoryConflictError,
)

UTC = timezone.utc


def make_series(series_id: str = "series-1", fixture_id: str = "fixture-1") -> QuoteSeries:
    return QuoteSeries(
        series_id=series_id,
        fixture_id=fixture_id,
        bookmaker_id=10,
        market=Market.OU_25,
        selection=Selection.OVER,
        created_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
    )


def make_snapshot(snapshot_id: str, odd: float = 2.10, series_id: str = "series-1") -> QuoteSnapshot:
    return QuoteSnapshot(
        snapshot_id=snapshot_id,
        series_id=series_id,
        odd=odd,
        observed_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        captured_at=datetime(2026, 9, 14, 12, 0, 1, tzinfo=UTC),
        source="api-football",
    )


def test_ensure_series_is_idempotent_and_queryable_by_fixture() -> None:
    repository = InMemoryQuoteHistoryRepository()
    series = make_series()
    repository.ensure_series(series)
    repository.ensure_series(series)
    assert repository.series_for_fixture("fixture-1") == (series,)


def test_ensure_series_rejects_conflicting_definition() -> None:
    repository = InMemoryQuoteHistoryRepository()
    repository.ensure_series(make_series())
    with pytest.raises(QuoteHistoryConflictError, match="series ID"):
        repository.ensure_series(make_series(fixture_id="fixture-2"))


def test_append_snapshots_preserves_history_and_is_idempotent() -> None:
    repository = InMemoryQuoteHistoryRepository()
    repository.ensure_series(make_series())
    first = make_snapshot("snapshot-1", odd=2.10)
    second = make_snapshot("snapshot-2", odd=2.25)
    repository.append_snapshots([first, second])
    repository.append_snapshots([first])
    assert repository.snapshots_for_series("series-1") == (first, second)
    assert repository.get_snapshot("snapshot-1") == first
    assert repository.get_snapshot("missing") is None


def test_snapshots_for_series_filters_other_series() -> None:
    repository = InMemoryQuoteHistoryRepository()
    repository.ensure_series(make_series("series-1"))
    repository.ensure_series(make_series("series-2"))
    first = make_snapshot("snapshot-1", series_id="series-1")
    other = make_snapshot("snapshot-2", series_id="series-2")
    repository.append_snapshots([first, other])
    assert repository.snapshots_for_series("series-1") == (first,)
    assert repository.snapshots_for_series("series-2") == (other,)


def test_append_snapshots_rejects_unknown_series() -> None:
    repository = InMemoryQuoteHistoryRepository()
    with pytest.raises(QuoteHistoryConflictError, match="unknown series ID"):
        repository.append_snapshots([make_snapshot("snapshot-1")])


def test_append_snapshots_is_atomic_on_conflict() -> None:
    repository = InMemoryQuoteHistoryRepository()
    repository.ensure_series(make_series())
    first = make_snapshot("snapshot-1", odd=2.10)
    repository.append_snapshots([first])
    with pytest.raises(QuoteHistoryConflictError, match="snapshot ID"):
        repository.append_snapshots([
            make_snapshot("snapshot-2", odd=2.30),
            make_snapshot("snapshot-1", odd=2.40),
        ])
    assert repository.snapshots_for_series("series-1") == (first,)
    assert repository.get_snapshot("snapshot-2") is None


def test_append_snapshots_rejects_conflicting_duplicate_ids_in_same_batch() -> None:
    repository = InMemoryQuoteHistoryRepository()
    repository.ensure_series(make_series())
    first = make_snapshot("snapshot-1", odd=2.10)
    conflicting = make_snapshot("snapshot-1", odd=2.20)
    with pytest.raises(QuoteHistoryConflictError, match="snapshot ID"):
        repository.append_snapshots([first, conflicting])
    assert repository.get_snapshot("snapshot-1") is None
