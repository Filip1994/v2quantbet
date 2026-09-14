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
        self.rows: list[tuple] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self.connection.executed.append((sql, params))
        if sql.startswith("SELECT 1 FROM quote_series"):
            self.result = (1,) if params[0] in self.connection.series_by_id else None
        elif "FROM quote_series WHERE series_id" in sql:
            self.result = self.connection.series_by_id.get(params[0])
        elif "FROM quote_series WHERE fixture_id" in sql:
            self.rows = [
                row
                for row in self.connection.series_rows
                if row[1] == params[0]
            ]
        elif "FROM quote_snapshots WHERE snapshot_id" in sql:
            self.result = self.connection.snapshots_by_id.get(params[0])
        elif "FROM quote_snapshots WHERE series_id" in sql:
            self.rows = [
                row
                for row in self.connection.snapshot_rows
                if row[1] == params[0]
            ]
        elif sql.startswith("INSERT INTO quote_series"):
            self.connection.series_by_id[params[0]] = params[1:]
            self.connection.series_rows.append((params[0], *params[1:]))
            self.result = None
        elif sql.startswith("INSERT INTO quote_snapshots"):
            self.connection.snapshots_by_id[params[0]] = params[1:]
            self.connection.snapshot_rows.append((params[0], *params[1:]))
            self.result = None

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self) -> None:
        self.series_by_id: dict[str, tuple] = {}
        self.snapshots_by_id: dict[str, tuple] = {}
        self.series_rows: list[tuple] = []
        self.snapshot_rows: list[tuple] = []
        self.executed: list[tuple[str, object]] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def seed_series(connection: FakeConnection) -> QuoteSeries:
    series = make_series()
    connection.series_by_id[series.series_id] = (
        series.fixture_id,
        series.bookmaker_id,
        series.market.value,
        series.selection.value,
        series.created_at,
    )
    connection.series_rows.append(
        (
            series.series_id,
            series.fixture_id,
            series.bookmaker_id,
            series.market.value,
            series.selection.value,
            series.created_at,
        )
    )
    return series


def seed_snapshot(connection: FakeConnection) -> QuoteSnapshot:
    snapshot = make_snapshot()
    connection.snapshots_by_id[snapshot.snapshot_id] = (
        snapshot.series_id,
        snapshot.odd,
        snapshot.observed_at,
        snapshot.captured_at,
        snapshot.source,
    )
    connection.snapshot_rows.append(
        (
            snapshot.snapshot_id,
            snapshot.series_id,
            snapshot.odd,
            snapshot.observed_at,
            snapshot.captured_at,
            snapshot.source,
        )
    )
    return snapshot


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
        (
            series.series_id,
            series.fixture_id,
            series.bookmaker_id,
            series.market.value,
            series.selection.value,
            series.created_at,
        )
    )
    restored_snapshot = PostgreSQLQuoteHistoryRepository._row_to_snapshot(
        (
            snapshot.snapshot_id,
            snapshot.series_id,
            snapshot.odd,
            snapshot.observed_at,
            snapshot.captured_at,
            snapshot.source,
        )
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


def test_series_for_fixture_reconstructs_rows() -> None:
    connection = FakeConnection()
    series = seed_series(connection)
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    assert repository.series_for_fixture(series.fixture_id) == (series,)


def test_append_snapshots_rejects_unknown_series() -> None:
    connection = FakeConnection()
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    with pytest.raises(QuoteHistoryConflictError, match="unknown series ID"):
        repository.append_snapshots((make_snapshot(),))


def test_append_snapshots_inserts_snapshot_for_known_series() -> None:
    connection = FakeConnection()
    series = seed_series(connection)
    snapshot = make_snapshot()
    assert snapshot.series_id == series.series_id
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    repository.append_snapshots((snapshot,))

    assert "snapshot-1" in connection.snapshots_by_id


def test_append_snapshots_is_idempotent_for_matching_snapshot() -> None:
    connection = FakeConnection()
    seed_series(connection)
    snapshot = seed_snapshot(connection)
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    repository.append_snapshots((snapshot,))

    assert sum("INSERT INTO quote_snapshots" in sql for sql, _ in connection.executed) == 0


def test_append_snapshots_rejects_conflicting_snapshot() -> None:
    connection = FakeConnection()
    seed_series(connection)
    snapshot = seed_snapshot(connection)
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


def test_snapshots_for_series_reconstructs_rows() -> None:
    connection = FakeConnection()
    seed_series(connection)
    snapshot = seed_snapshot(connection)
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    assert repository.snapshots_for_series(snapshot.series_id) == (snapshot,)


def test_get_snapshot_returns_snapshot_when_present() -> None:
    connection = FakeConnection()
    seed_series(connection)
    snapshot = seed_snapshot(connection)
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    assert repository.get_snapshot(snapshot.snapshot_id) == snapshot


def test_get_snapshot_returns_none_when_missing() -> None:
    connection = FakeConnection()
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)

    assert repository.get_snapshot("missing") is None
