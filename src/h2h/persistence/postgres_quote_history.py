"""PostgreSQL persistence for immutable quote history."""

import os
from collections.abc import Callable, Iterable
from typing import Any

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.persistence.quote_history import QuoteHistoryConflictError


ConnectionFactory = Callable[[], Any]


class PostgreSQLQuoteHistoryRepository:
    """PostgreSQL implementation of the quote-history repository contract."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        connect: ConnectionFactory | None = None,
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect

    def connect(self) -> Any:
        """Open a database connection for an application-level operation."""
        if self._connect_factory is not None:
            return self._connect_factory()
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires the optional 'psycopg[binary]' dependency"
            ) from exc
        return psycopg.connect(self._database_url)

    def ensure_series(self, series: QuoteSeries) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE series_id = %s",
                (series.series_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                self._require_same_series(row, series)
                return
            cursor.execute(
                "INSERT INTO quote_series "
                "(series_id, fixture_id, bookmaker_id, market, selection, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    series.series_id,
                    series.fixture_id,
                    series.bookmaker_id,
                    series.market.value,
                    series.selection.value,
                    series.created_at,
                ),
            )
            cursor.execute(
                "SELECT fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE series_id = %s",
                (series.series_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise QuoteHistoryConflictError(
                    f"conflicting definition for series ID {series.series_id!r}"
                )
            self._require_same_series(row, series)

    def find_series(self, *, fixture_id: str, bookmaker_id: int, market: str, selection: str) -> QuoteSeries | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT series_id, fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE fixture_id = %s AND bookmaker_id = %s "
                "AND market = %s AND selection = %s",
                (fixture_id, bookmaker_id, market, selection),
            )
            row = cursor.fetchone()
            return None if row is None else self._row_to_series(row)

    def series_for_fixture(self, fixture_id: str) -> tuple[QuoteSeries, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT series_id, fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE fixture_id = %s ORDER BY created_at, series_id",
                (fixture_id,),
            )
            return tuple(self._row_to_series(row) for row in cursor.fetchall())

    def append_snapshots(self, snapshots: Iterable[QuoteSnapshot]) -> None:
        """Append snapshots atomically using semantic observation identity.

        The natural key is (series_id, observed_at, source). captured_at is
        metadata only. An identical replay is accepted; a changed odd for the
        same natural key is rejected.
        """
        incoming = tuple(snapshots)
        if not incoming:
            return
        with self.connect() as connection, connection.cursor() as cursor:
            series_ids = tuple({snapshot.series_id for snapshot in incoming})
            cursor.execute(
                "SELECT series_id FROM quote_series WHERE series_id = ANY(%s)",
                (list(series_ids),),
            )
            known_series = {row[0] for row in cursor.fetchall()}
            for series_id in series_ids:
                if series_id not in known_series:
                    raise QuoteHistoryConflictError(f"unknown series ID {series_id!r}")

            for snapshot in incoming:
                cursor.execute(
                    "SELECT snapshot_id, series_id, odd, observed_at, captured_at, source "
                    "FROM quote_snapshots WHERE series_id = %s AND observed_at = %s AND source = %s",
                    (snapshot.series_id, snapshot.observed_at, snapshot.source),
                )
                row = cursor.fetchone()
                if row is not None:
                    existing = tuple(row)
                    expected = (
                        snapshot.snapshot_id,
                        snapshot.series_id,
                        snapshot.odd,
                        snapshot.observed_at,
                        snapshot.captured_at,
                        snapshot.source,
                    )
                    if existing[1] != snapshot.series_id or existing[2] != snapshot.odd:
                        raise QuoteHistoryConflictError(
                            "conflicting observation for semantic quote identity"
                        )
                    continue

                cursor.execute(
                    "INSERT INTO quote_snapshots "
                    "(snapshot_id, series_id, odd, observed_at, captured_at, source) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        snapshot.snapshot_id,
                        snapshot.series_id,
                        snapshot.odd,
                        snapshot.observed_at,
                        snapshot.captured_at,
                        snapshot.source,
                    ),
                )

    @staticmethod
    def _require_same_series(row: tuple[Any, ...], series: QuoteSeries) -> None:
        expected = (
            series.fixture_id,
            series.bookmaker_id,
            series.market.value,
            series.selection.value,
            series.created_at,
        )
        if tuple(row) != expected:
            raise QuoteHistoryConflictError(
                f"conflicting definition for series ID {series.series_id!r}"
            )

    @staticmethod
    def _row_to_series(row: tuple[Any, ...]) -> QuoteSeries:
        return QuoteSeries(row[0], row[1], row[2], Market(row[3]), Selection(row[4]), row[5])

    def snapshots_for_series(self, series_id: str) -> tuple[QuoteSnapshot, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT snapshot_id, series_id, odd, observed_at, captured_at, source "
                "FROM quote_snapshots WHERE series_id = %s ORDER BY observed_at, captured_at, snapshot_id",
                (series_id,),
            )
            return tuple(self._row_to_snapshot(row) for row in cursor.fetchall())

    def get_snapshot(self, snapshot_id: str) -> QuoteSnapshot | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT snapshot_id, series_id, odd, observed_at, captured_at, source "
                "FROM quote_snapshots WHERE snapshot_id = %s",
                (snapshot_id,),
            )
            row = cursor.fetchone()
            return None if row is None else self._row_to_snapshot(row)

    @staticmethod
    def _row_to_snapshot(row: tuple[Any, ...]) -> QuoteSnapshot:
        return QuoteSnapshot(row[0], row[1], row[2], row[3], row[4], row[5])
