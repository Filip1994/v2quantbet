from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.persistence.postgres_quote_history import PostgreSQLQuoteHistoryRepository
from h2h.persistence.quote_history import QuoteHistoryConflictError

UTC = timezone.utc


@pytest.mark.parametrize("new_id", [False, True])
@pytest.mark.parametrize("later_capture", [False, True])
def test_semantic_replay_preserves_original_snapshot(new_id, later_capture):
    connection = FakeConnection()
    seed_series(connection)
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)
    first = make_snapshot()
    replay = replace(
        first,
        snapshot_id="replay" if new_id else first.snapshot_id,
        captured_at=first.captured_at + timedelta(seconds=int(later_capture)),
    )
    repository.append_snapshots([first])
    repository.append_snapshots([replay])
    assert repository.snapshots_for_series(first.series_id) == (first,)
    assert repository.get_snapshot(first.snapshot_id) == first
    if new_id:
        assert repository.get_snapshot(replay.snapshot_id) is None


@pytest.mark.parametrize("field", ["observed_at", "source"])
def test_distinct_semantic_observations_are_preserved(field):
    connection = FakeConnection()
    seed_series(connection)
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)
    first = make_snapshot()
    value = first.observed_at + timedelta(seconds=1) if field == "observed_at" else "other-source"
    second = replace(first, snapshot_id="second", **{field: value})
    repository.append_snapshots([first, second])
    assert repository.snapshots_for_series(first.series_id) == (first, second)


@pytest.mark.parametrize("field", ["odd", "observed_at", "source"])
def test_snapshot_id_cannot_change_observation(field):
    connection = FakeConnection()
    seed_series(connection)
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)
    first = make_snapshot()
    value = {"odd": 2.5, "observed_at": first.observed_at + timedelta(seconds=1), "source": "other"}[field]
    repository.append_snapshots([first])
    with pytest.raises(QuoteHistoryConflictError, match="snapshot ID"):
        repository.append_snapshots([replace(first, **{field: value})])
    assert repository.get_snapshot(first.snapshot_id) == first


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
        self.result = None
        self.rows = []
        if sql.startswith("SELECT series_id FROM quote_series WHERE series_id = ANY"):
            self.rows = [
                (series_id,)
                for series_id in params[0]
                if series_id in self.connection.series_by_id
            ]
        elif "FROM quote_series WHERE series_id" in sql:
            self.result = self.connection.series_by_id.get(params[0])
        elif "FROM quote_series WHERE fixture_id" in sql:
            self.rows = [row for row in self.connection.series_rows if row[1] == params[0]]
            if len(params) == 4:
                self.rows = [
                    row
                    for row in self.rows
                    if row[2] == params[1]
                    and row[3] == params[2]
                    and row[4] == params[3]
                ]
            self.result = self.rows[0] if self.rows else None
        elif "FROM quote_snapshots WHERE snapshot_id" in sql:
            stored = self.connection.snapshots_by_id.get(params[0])
            if stored is None:
                self.result = None
            elif "SELECT snapshot_id" in sql:
                self.result = (params[0], *stored)
            else:
                self.result = stored
        elif "FROM quote_snapshots WHERE series_id = %s AND observed_at" in sql:
            self.result = next(
                (
                    row
                    for row in self.connection.snapshot_rows
                    if row[1] == params[0]
                    and row[3] == params[1]
                    and row[5] == params[2]
                ),
                None,
            )
        elif "FROM quote_snapshots WHERE series_id" in sql:
            self.rows = [row for row in self.connection.snapshot_rows if row[1] == params[0]]
        elif sql.startswith("INSERT INTO quote_series"):
            self.connection.series_by_id[params[0]] = params[1:]
            self.connection.series_rows.append((params[0], *params[1:]))
        elif sql.startswith("INSERT INTO quote_snapshots"):
            # Control-flow double only: real SQL compatibility is tested in integration.
            if any(
                (row[1], row[3], row[5]) == (params[1], params[3], params[5])
                for row in self.connection.snapshot_rows
            ):
                return
            self.connection.snapshots_by_id[params[0]] = params[1:]
            self.connection.snapshot_rows.append((params[0], *params[1:]))

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
    row = (
        series.series_id,
        series.fixture_id,
        series.bookmaker_id,
        series.market.value,
        series.selection.value,
        series.created_at,
    )
    connection.series_by_id[series.series_id] = row[1:]
    connection.series_rows.append(row)
    return series


def seed_snapshot(connection: FakeConnection) -> QuoteSnapshot:
    snapshot = make_snapshot()
    row = (
        snapshot.snapshot_id,
        snapshot.series_id,
        snapshot.odd,
        snapshot.observed_at,
        snapshot.captured_at,
        snapshot.source,
    )
    connection.snapshots_by_id[snapshot.snapshot_id] = row[1:]
    connection.snapshot_rows.append(row)
    return snapshot


def repository(connection: FakeConnection) -> PostgreSQLQuoteHistoryRepository:
    return PostgreSQLQuoteHistoryRepository(connect=lambda: connection)


def test_requires_database_url_without_injected_connection() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        PostgreSQLQuoteHistoryRepository(database_url="")


def test_injected_connection_factory_takes_precedence() -> None:
    connection = object()
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)
    assert repository.connect() is connection


def test_row_conversion_reconstructs_domain_objects() -> None:
    series = make_series()
    snapshot = make_snapshot()
    assert PostgreSQLQuoteHistoryRepository._row_to_series(
        (series.series_id, series.fixture_id, series.bookmaker_id, series.market.value, series.selection.value, series.created_at)
    ) == series
    assert PostgreSQLQuoteHistoryRepository._row_to_snapshot(
        (snapshot.snapshot_id, snapshot.series_id, snapshot.odd, snapshot.observed_at, snapshot.captured_at, snapshot.source)
    ) == snapshot


def test_ensure_series_inserts_missing_series() -> None:
    connection = FakeConnection()
    repository(connection).ensure_series(make_series())
    assert "series-1" in connection.series_by_id


def test_ensure_series_rejects_conflict() -> None:
    series = make_series()
    connection = FakeConnection()
    connection.series_by_id[series.series_id] = (
        series.fixture_id, series.bookmaker_id, series.market.value, Selection.UNDER.value, series.created_at
    )
    with pytest.raises(QuoteHistoryConflictError):
        repository(connection).ensure_series(series)


def test_find_series_returns_matching_natural_identity() -> None:
    connection = FakeConnection()
    series = seed_series(connection)
    assert repository(connection).find_series(
        fixture_id=series.fixture_id,
        bookmaker_id=series.bookmaker_id,
        market=series.market,
        selection=series.selection,
    ) == series


def test_find_series_returns_none_for_missing_identity() -> None:
    assert repository(FakeConnection()).find_series(
        fixture_id="missing",
        bookmaker_id=10,
        market=Market.OU_25,
        selection=Selection.OVER,
    ) is None


def test_find_series_distinguishes_selection() -> None:
    connection = FakeConnection()
    seed_series(connection)
    assert repository(connection).find_series(
        fixture_id="fixture-1",
        bookmaker_id=10,
        market=Market.OU_25,
        selection=Selection.UNDER,
    ) is None


def test_series_for_fixture_reconstructs_rows() -> None:
    connection = FakeConnection()
    series = seed_series(connection)
    assert repository(connection).series_for_fixture(series.fixture_id) == (series,)


def test_append_snapshots_rejects_unknown_series() -> None:
    with pytest.raises(QuoteHistoryConflictError, match="unknown series ID"):
        repository(FakeConnection()).append_snapshots((make_snapshot(),))


def test_append_and_read_snapshot() -> None:
    connection = FakeConnection()
    seed_series(connection)
    snapshot = make_snapshot()
    repository(connection).append_snapshots((snapshot,))
    assert repository(connection).get_snapshot(snapshot.snapshot_id) == snapshot
    assert repository(connection).snapshots_for_series(snapshot.series_id) == (snapshot,)


def test_append_snapshots_is_idempotent_for_matching_snapshot() -> None:
    connection = FakeConnection()
    seed_series(connection)
    snapshot = seed_snapshot(connection)
    repository(connection).append_snapshots((snapshot,))
    assert sum("INSERT INTO quote_snapshots" in sql for sql, _ in connection.executed) == 0


def test_append_snapshots_rejects_conflicting_snapshot() -> None:
    connection = FakeConnection()
    seed_series(connection)
    snapshot = seed_snapshot(connection)
    connection.snapshots_by_id[snapshot.snapshot_id] = (
        snapshot.series_id, 2.20, snapshot.observed_at, snapshot.captured_at, snapshot.source
    )
    with pytest.raises(QuoteHistoryConflictError, match="snapshot ID"):
        repository(connection).append_snapshots((snapshot,))


def test_get_snapshot_returns_none_when_missing() -> None:
    assert repository(FakeConnection()).get_snapshot("missing") is None


def test_changed_odd_conflicts_after_semantic_insert_noop():
    connection = FakeConnection()
    seed_series(connection)
    first = seed_snapshot(connection)
    with pytest.raises(QuoteHistoryConflictError, match="semantic quote identity"):
        repository(connection).append_snapshots([replace(first, snapshot_id="replay", odd=2.5)])
    assert repository(connection).snapshots_for_series(first.series_id) == (first,)


def test_insert_and_lookup_use_three_column_semantic_key():
    connection = FakeConnection()
    seed_series(connection)
    repository(connection).append_snapshots([make_snapshot()])
    inserts = [sql for sql, _ in connection.executed if sql.startswith("INSERT INTO quote_snapshots")]
    assert "ON CONFLICT (series_id, observed_at, source) DO NOTHING" in inserts[0]
    lookups = [(sql, params) for sql, params in connection.executed if "AND observed_at" in sql]
    assert "AND captured_at" not in lookups[0][0]
    assert len(lookups[0][1]) == 3
