"""PostgreSQL persistence for immutable quote history.

The PostgreSQL driver is imported lazily so the provider-neutral domain and
in-memory repositories remain usable in environments that do not yet install
production database dependencies.
"""

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING
from datetime import datetime
import os

from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.persistence.quote_history import QuoteHistoryConflictError

if TYPE_CHECKING:
    import psycopg


class PostgreSQLQuoteHistoryRepository:
    """PostgreSQL implementation of the quote-history repository contract."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url:
            raise ValueError("DATABASE_URL is required")

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires the optional 'psycopg[binary]' dependency"
            ) from exc
        return psycopg.connect(self._database_url)

    def ensure_series(self, series: QuoteSeries) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE series_id = %s", (series.series_id,))
            row = cursor.fetchone()
            if row is not None:
                expected = (series.fixture_id, series.bookmaker_id, series.market.value,
                            series.selection.value, series.created_at)
                if tuple(row) != expected:
                    raise QuoteHistoryConflictError(
                        f"conflicting definition for series ID {series.series_id!r}")
                return
            cursor.execute(
                "INSERT INTO quote_series "
                "(series_id, fixture_id, bookmaker_id, market, selection, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (series.series_id, series.fixture_id, series.bookmaker_id,
                 series.market.value, series.selection.value, series.created_at))

    def series_for_fixture(self, fixture_id: str) -> tuple[QuoteSeries, ...]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT series_id, fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE fixture_id = %s ORDER BY created_at, series_id",
                (fixture_id,))
            return tuple(self._row_to_series(row) for row in cursor.fetchall())

    def append_snapshots(self, snapshots: Iterable[QuoteSnapshot]) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            for snapshot in tuple(snapshots):
                cursor.execute("SELECT 1 FROM quote_series WHERE series_id = %s",
                               (snapshot.series_id,))
                if cursor.fetchone() is None:
                    raise QuoteHistoryConflictError(f"unknown series ID {snapshot.series_id!r}")
                cursor.execute(
                    "SELECT series_id, odd, observed_at, captured_at, source "
                    "FROM quote_snapshots WHERE snapshot_id = %s", (snapshot.snapshot_id,))
                row = cursor.fetchone()
                if row is not None:
                    expected = (snapshot.series_id, snapshot.odd, snapshot.observed_at,
                                snapshot.captured_at, snapshot.source)
                    if tuple(row) != expected:
                        raise QuoteHistoryConflictError(
                            f"conflicting observation for snapshot ID {snapshot.snapshot_id!r}")
                    continue
                cursor.execute(
                    "INSERT INTO quote_snapshots "
                    "(snapshot_id, series_id, odd, observed_at, captured_at, source) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (snapshot.snapshot_id, snapshot.series_id, snapshot.odd,
                     snapshot.observed_at, snapshot.captured_at, snapshot.source))

    def snapshots_for_series(self, series_id: str) -> tuple[QuoteSnapshot, ...]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT snapshot_id, series_id, odd, observed_at, captured_at, source "
                "FROM quote_snapshots WHERE series_id = %s ORDER BY observed_at, captured_at, snapshot_id",
                (series_id,))
            return tuple(self._row_to_snapshot(row) for row in cursor.fetchall())

    def get_snapshot(self, snapshot_id: str) -> QuoteSnapshot | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT snapshot_id, series_id, odd, observed_at, captured_at, source "
                "FROM quote_snapshots WHERE snapshot_id = %s", (snapshot_id,))
            row = cursor.fetchone()
            return None if row is None else self._row_to_snapshot(row)

    @staticmethod
    def _row_to_series(row):
        from h2h.domain.odds import Market, Selection
        return QuoteSeries(row[0], row[1], row[2], Market(row[3]), Selection(row[4]), row[5])

    @staticmethod
    def _row_to_snapshot(row):
        return QuoteSnapshot(row[0], row[1], row[2], row[3], row[4], row[5])
