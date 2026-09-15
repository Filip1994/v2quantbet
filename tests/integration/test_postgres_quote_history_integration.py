from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.odds import Market, Selection  # noqa: E402
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot  # noqa: E402
from h2h.persistence.postgres_quote_history import (  # noqa: E402
    PostgreSQLQuoteHistoryRepository,
)
from h2h.persistence.quote_history import QuoteHistoryConflictError  # noqa: E402


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
UTC = timezone.utc


def _migration_sql() -> str:
    return (Path(__file__).parents[2] / "migrations" / "001_quote_history.sql").read_text()


def _series(*, series_id: str, fixture_id: str) -> QuoteSeries:
    return QuoteSeries(
        series_id=series_id,
        fixture_id=fixture_id,
        bookmaker_id=10,
        market=Market.OU_25,
        selection=Selection.OVER,
        created_at=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
    )


def _snapshot(
    *,
    snapshot_id: str,
    series_id: str,
    odd: float = 2.1,
    captured_at: datetime | None = None,
) -> QuoteSnapshot:
    return QuoteSnapshot(
        snapshot_id=snapshot_id,
        series_id=series_id,
        odd=odd,
        observed_at=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        captured_at=captured_at or datetime(2026, 9, 15, 12, 0, 1, tzinfo=UTC),
        source="integration-test",
    )


@pytest.fixture
def repository():
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(_migration_sql())

    repo = PostgreSQLQuoteHistoryRepository(database_url=DATABASE_URL)
    prefix = f"it-{uuid4()}"
    created_series: list[str] = []
    created_snapshots: list[str] = []

    class Context:
        pass

    context = Context()
    context.repo = repo
    context.prefix = prefix
    context.created_series = created_series
    context.created_snapshots = created_snapshots
    yield context

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            if created_snapshots:
                cursor.execute(
                    "DELETE FROM quote_snapshots WHERE snapshot_id = ANY(%s)",
                    (created_snapshots,),
                )
            if created_series:
                cursor.execute(
                    "DELETE FROM quote_series WHERE series_id = ANY(%s)",
                    (created_series,),
                )


def test_natural_series_conflict_is_detected(repository) -> None:
    first = _series(series_id=f"{repository.prefix}-series-a", fixture_id=f"{repository.prefix}-fixture")
    second = _series(series_id=f"{repository.prefix}-series-b", fixture_id=first.fixture_id)
    repository.repo.ensure_series(first)
    repository.created_series.append(first.series_id)

    with pytest.raises(QuoteHistoryConflictError):
        repository.repo.ensure_series(second)


def test_identical_series_retry_is_idempotent(repository) -> None:
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    repository.repo.ensure_series(series)
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    assert repository.repo.series_for_fixture(series.fixture_id) == (series,)


def test_snapshot_conflict_is_rejected(repository) -> None:
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    snapshot = _snapshot(snapshot_id=f"{repository.prefix}-snapshot", series_id=series.series_id)
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    repository.repo.append_snapshots((snapshot,))
    repository.created_snapshots.append(snapshot.snapshot_id)

    conflicting = _snapshot(
        snapshot_id=snapshot.snapshot_id,
        series_id=series.series_id,
        odd=2.2,
    )
    with pytest.raises(QuoteHistoryConflictError):
        repository.repo.append_snapshots((conflicting,))


def test_duplicate_snapshot_natural_key_is_rejected(repository) -> None:
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    first = _snapshot(snapshot_id=f"{repository.prefix}-snapshot-a", series_id=series.series_id)
    second = _snapshot(snapshot_id=f"{repository.prefix}-snapshot-b", series_id=series.series_id)
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    repository.repo.append_snapshots((first,))
    repository.created_snapshots.append(first.snapshot_id)

    with pytest.raises(QuoteHistoryConflictError):
        repository.repo.append_snapshots((second,))


def test_snapshot_natural_key_includes_captured_at(repository) -> None:
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    first = _snapshot(snapshot_id=f"{repository.prefix}-snapshot-a", series_id=series.series_id)
    second = _snapshot(
        snapshot_id=f"{repository.prefix}-snapshot-b",
        series_id=series.series_id,
        captured_at=first.captured_at + timedelta(seconds=1),
    )
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    repository.repo.append_snapshots((first, second))
    repository.created_snapshots.extend([first.snapshot_id, second.snapshot_id])

    assert repository.repo.snapshots_for_series(series.series_id) == (first, second)
