from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_quote_history import (
    PostgreSQLQuoteHistoryRepository,
)
from h2h.persistence.quote_history import QuoteHistoryConflictError


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
UTC = timezone.utc


MIGRATION_DIR = Path(__file__).parents[2] / "migrations"


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
    observed_at: datetime | None = None,
) -> QuoteSnapshot:
    return QuoteSnapshot(
        snapshot_id=snapshot_id,
        series_id=series_id,
        odd=odd,
        observed_at=observed_at or datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        captured_at=captured_at or datetime(2026, 9, 15, 12, 0, 1, tzinfo=UTC),
        source="integration-test",
    )


@pytest.fixture
def repository():
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        apply_migrations(connection, MIGRATION_DIR)

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

    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
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


def test_changed_odd_for_semantic_identity_is_rejected(repository) -> None:
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    first = _snapshot(snapshot_id=f"{repository.prefix}-snapshot-a", series_id=series.series_id)
    second = _snapshot(snapshot_id=f"{repository.prefix}-snapshot-b", series_id=series.series_id, odd=2.2)
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    repository.repo.append_snapshots((first,))
    repository.created_snapshots.append(first.snapshot_id)

    with pytest.raises(QuoteHistoryConflictError):
        repository.repo.append_snapshots((second,))


def test_snapshot_replay_preserves_original_capture_time(repository) -> None:
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

    assert repository.repo.snapshots_for_series(series.series_id) == (first,)
    assert repository.repo.get_snapshot(second.snapshot_id) is None


def test_snapshot_batch_conflict_rolls_back_prior_inserts(repository) -> None:
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    existing = _snapshot(snapshot_id=f"{repository.prefix}-existing", series_id=series.series_id)
    new_snapshot = _snapshot(
        snapshot_id=f"{repository.prefix}-new",
        series_id=series.series_id,
        observed_at=existing.observed_at + timedelta(seconds=1),
        captured_at=existing.captured_at + timedelta(seconds=1),
    )
    conflicting = _snapshot(
        snapshot_id=f"{repository.prefix}-conflict",
        series_id=series.series_id,
        odd=2.2,
    )
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    repository.repo.append_snapshots((existing,))
    repository.created_snapshots.append(existing.snapshot_id)

    with pytest.raises(QuoteHistoryConflictError):
        repository.repo.append_snapshots((new_snapshot, conflicting))

    assert repository.repo.get_snapshot(new_snapshot.snapshot_id) is None
    assert repository.repo.get_snapshot(existing.snapshot_id) == existing


def test_complete_migration_chain_is_applied(repository):
    with repository.repo.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations")
        versions = {row[0] for row in cursor.fetchall()}
        assert {path.name for path in MIGRATION_DIR.glob("*.sql")} <= versions
        assert "002_quote_snapshot_observation_identity.sql" in versions
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'quote_snapshots'::regclass AND contype = 'u'"
        )
        assert {row[0] for row in cursor.fetchall()} == {"UNIQUE (series_id, observed_at, source)"}
    with repository.repo.connect() as connection:
        assert apply_migrations(connection, MIGRATION_DIR) == ()


@pytest.mark.parametrize("new_id", [False, True])
@pytest.mark.parametrize("later_capture", [False, True])
def test_fresh_insert_and_semantic_replay(repository, new_id, later_capture):
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    first = _snapshot(snapshot_id=f"{repository.prefix}-first", series_id=series.series_id)
    replay = replace(
        first,
        snapshot_id=f"{repository.prefix}-replay" if new_id else first.snapshot_id,
        captured_at=first.captured_at + timedelta(seconds=int(later_capture)),
    )
    repository.created_snapshots.extend([first.snapshot_id, replay.snapshot_id])
    repository.repo.append_snapshots([first])
    assert repository.repo.get_snapshot(first.snapshot_id) == first
    repository.repo.append_snapshots([replay])
    assert repository.repo.snapshots_for_series(series.series_id) == (first,)
    if new_id:
        assert repository.repo.get_snapshot(replay.snapshot_id) is None


@pytest.mark.parametrize("field", ["observed_at", "source"])
def test_distinct_semantic_observation_inserts(repository, field):
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    first = _snapshot(snapshot_id=f"{repository.prefix}-first", series_id=series.series_id)
    value = first.observed_at + timedelta(seconds=1) if field == "observed_at" else "other-source"
    second = replace(first, snapshot_id=f"{repository.prefix}-second", **{field: value})
    repository.created_snapshots.extend([first.snapshot_id, second.snapshot_id])
    repository.repo.append_snapshots([first, second])
    assert repository.repo.snapshots_for_series(series.series_id) == (first, second)


@pytest.mark.parametrize("field", ["observed_at", "source"])
def test_snapshot_id_cannot_be_reused_for_other_observation(repository, field):
    series = _series(series_id=f"{repository.prefix}-series", fixture_id=f"{repository.prefix}-fixture")
    repository.repo.ensure_series(series)
    repository.created_series.append(series.series_id)
    first = _snapshot(snapshot_id=f"{repository.prefix}-first", series_id=series.series_id)
    repository.created_snapshots.append(first.snapshot_id)
    repository.repo.append_snapshots([first])
    value = first.observed_at + timedelta(seconds=1) if field == "observed_at" else "other-source"
    with pytest.raises(QuoteHistoryConflictError, match="snapshot ID"):
        repository.repo.append_snapshots([replace(first, **{field: value})])
    assert repository.repo.get_snapshot(first.snapshot_id) == first
