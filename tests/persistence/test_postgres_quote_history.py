from datetime import datetime, timezone

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.persistence.postgres_quote_history import PostgreSQLQuoteHistoryRepository
from h2h.persistence.quote_history import QuoteHistoryConflictError

UTC = timezone.utc


def make_series() -> QuoteSeries:
    return QuoteSeries(
        series_id="series-1",
        fixture_id="fixture-1",
        bookmaker_id=10,
        market=Market.OU_25,
        selection=Selection.OVER,
        created_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
    )


def make_snapshot() -> QuoteSnapshot:
    return QuoteSnapshot(
        snapshot_id="snapshot-1",
        series_id="series-1",
        odd=2.10,
        observed_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        captured_at=datetime(2026, 9, 14, 12, 0, 1, tzinfo=UTC),
        source="api-football",
    )


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.result: tuple | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self.connection.executed.append((sql, params))
        if "FROM quote_series WHERE series_id" in sql:
            self.result = self.connection.series_by_id.get(params[0])
        elif "FROM quote_snapshots WHERE snapshot_id" in sql:
            self.result = self.connection.snapshots_by_id.get(params[0])
        elif sql.startswith("SELECT 1 FROM quote_series"):
            self.result = (1,) if params[0] in self.connection.series_by_id else None
        elif sql.startswith("INSERT INTO quote_series"):
            self.connection.series_by_id[params[0]] = params
            self.result = None
        elif sql.startswith("INSERT INTO quote_snapshots"):
            self.connection.snapshots_by_id[params[0]] = params
            self.result = None

    def fetchone(self):
        return self.result

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self) -> None:
        self.series_by_id: dict[str, tuple] = {}
        self.snapshots_by_id: dict[str, tuple] = {}
        self.executed: list[tuple[str, object]] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_requires_database_url_without_injected_connection() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        PostgreSQLQuoteHistoryRepository(database_url="")


def test_injected_connection_factory_allows_driver_free_construction() -> None:
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: object())
    assert repository._connect() is not None


def test_row_conversion_reconstructs_domain_objects() -> None:
    series = make_series()
    snapshot = make_snapshot()

    restored_series = PostgreSQLQuoteHistoryRepository._row_to_series(
        (series.series_id, series.fixture_id, series.bookmaker_id, series.market.value, series.selection.value, series.created_at)
    )
    restored_snapshot = PostgreSQLQuoteHistoryRepository._row_to_snapshot(
        (snapshot.snapshot_id, snapshot.series_id, snapshot.odd, snapshot.observed_at, snapshot.captured_at, snapshot.source)
    )

    assert restored_series == series
    assert restored_snapshot == snapshot


def test_injected_connection_factory_takes_precedence_over_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid")
    connection = object()
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)
    assert repository._connect() is connection


def test_ensure_series_inserts_missing_series() -> None:
    connection = FakeConnection()
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    repository.ensure_series(make_series())

    assert "INSERT INTO quote_series" in connection.executed[-1][0]
    assert "series-1" in connection.series_by_id


def test_ensure_series_rejects_conflicting_existing_series() -> None:
    series = make_series()
    connection = FakeConnection()
    connection.series_by_id[series.series_id] = (
        series.fixture_id,
        series.bookmaker_id,
        series.market.value,
        Selection.UNDER.value,
        series.created_at,
    )
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    with pytest.raises(QuoteHistoryConflictError):
        repository.ensure_series(series)


def test_append_snapshots_rejects_unknown_series() -> None:
    connection = FakeConnection()
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    with pytest.raises(QuoteHistoryConflictError, match="unknown series ID"):
        repository.append_snapshots((make_snapshot(),))


def test_append_snapshots_inserts_snapshot_for_known_series() -> None:
    series = make_series()
    snapshot = make_snapshot()
    connection = FakeConnection()
    connection.series_by_id[series.series_id] = (
        series.fixture_id,
        series.bookmaker_id,
        series.market.value,
        series.selection.value,
        series.created_at,
    )
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    repository.append_snapshots((snapshot,))

    assert "snapshot-1" in connection.snapshots_by_id


def test_append_snapshots_is_idempotent_for_matching_snapshot() -> None:
    series = make_series()
    snapshot = make_snapshot()
    connection = FakeConnection()
    connection.series_by_id[series.series_id] = (
        series.fixture_id,
        series.bookmaker_id,
        series.market.value,
        series.selection.value,
        series.created_at,
    )
    connection.snapshots_by_id[snapshot.snapshot_id] = (
        snapshot.series_id,
        snapshot.odd,
        snapshot.observed_at,
        snapshot.captured_at,
        snapshot.source,
    )
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    repository.append_snapshots((snapshot,))

    assert sum("INSERT INTO quote_snapshots" in sql for sql, _ in connection.executed) == 0


def test_append_snapshots_rejects_conflicting_snapshot() -> None:
    series = make_series()
    snapshot = make_snapshot()
    connection = FakeConnection()
    connection.series_by_id[series.series_id] = (
        series.fixture_id,
        series.bookmaker_id,
        series.market.value,
        series.selection.value,
        series.created_at,
    )
    connection.snapshots_by_id[snapshot.snapshot_id] = (
        snapshot.series_id,
        2.20,
        snapshot.observed_at,
        snapshot.captured_at,
        snapshot.source,
    )
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    with pytest.raises(QuoteHistoryConflictError, match="conflicting observation"):
        repository.append_snapshots((snapshot,))
