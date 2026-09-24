"""PostgreSQL persistence for immutable quote history."""

import os
from collections.abc import Callable, Iterable
from typing import Any

from h2h.domain.odds import Market, Selection
from h2h.domain.bookmaker_policy import API_FOOTBALL_BOOKMAKERS
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.domain.value_evaluation import PersistedMarketObservation, PersistedQuoteObservation
from h2h.persistence.quote_history import QuoteHistoryConflictError


ConnectionFactory = Callable[[], Any]


class PostgreSQLQuoteHistoryRepository:
    """PostgreSQL implementation of the quote-history repository contract."""

    def __init__(self, database_url: str | None = None, *, connect: ConnectionFactory | None = None) -> None:
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
                (series.series_id, series.fixture_id, series.bookmaker_id, series.market.value, series.selection.value, series.created_at),
            )
            cursor.execute(
                "SELECT fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE series_id = %s",
                (series.series_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise QuoteHistoryConflictError(f"conflicting definition for series ID {series.series_id!r}")
            self._require_same_series(row, series)

    def find_series(self, *, fixture_id: str, bookmaker_id: int, market: str, selection: str) -> QuoteSeries | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT series_id, fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE fixture_id = %s AND bookmaker_id = %s AND market = %s AND selection = %s",
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

    def fixture_ingestion_state(
        self, fixture_id: str
    ) -> tuple[tuple[QuoteSeries, ...], frozenset[tuple[str, Any, str]]]:
        """Load series definitions and semantic observation keys in one round-trip."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT s.series_id, s.fixture_id, s.bookmaker_id, s.market, s.selection, "
                "s.created_at, q.observed_at, q.source "
                "FROM quote_series s LEFT JOIN quote_snapshots q ON q.series_id = s.series_id "
                "WHERE s.fixture_id = %s ORDER BY s.created_at, s.series_id, q.observed_at",
                (fixture_id,),
            )
            rows = cursor.fetchall()

        series_by_id: dict[str, QuoteSeries] = {}
        observations: set[tuple[str, Any, str]] = set()
        for row in rows:
            series_id = str(row[0])
            series_by_id.setdefault(series_id, self._row_to_series(row[:6]))
            if row[6] is not None and row[7] is not None:
                observations.add((series_id, row[6], str(row[7])))
        return tuple(series_by_id.values()), frozenset(observations)

    def ensure_series_batch(self, series: Iterable[QuoteSeries]) -> None:
        """Ensure multiple series definitions using one transaction/connection."""
        incoming = tuple(series)
        if not incoming:
            return
        if len({item.series_id for item in incoming}) != len(incoming):
            raise QuoteHistoryConflictError("duplicate series ID in ingestion batch")

        with self.connect() as connection, connection.cursor() as cursor:
            for item in incoming:
                cursor.execute(
                    "INSERT INTO quote_series "
                    "(series_id, fixture_id, bookmaker_id, market, selection, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (
                        item.series_id,
                        item.fixture_id,
                        item.bookmaker_id,
                        item.market.value,
                        item.selection.value,
                        item.created_at,
                    ),
                )
            cursor.execute(
                "SELECT series_id, fixture_id, bookmaker_id, market, selection, created_at "
                "FROM quote_series WHERE series_id = ANY(%s)",
                ([item.series_id for item in incoming],),
            )
            persisted = {str(row[0]): row[1:] for row in cursor.fetchall()}
            for item in incoming:
                row = persisted.get(item.series_id)
                if row is None:
                    raise QuoteHistoryConflictError(
                        f"conflicting definition for series ID {item.series_id!r}"
                    )
                self._require_same_series(row, item)

    def append_snapshots(self, snapshots: Iterable[QuoteSnapshot]) -> None:
        """Append by (series_id, observed_at, source), preserving first provenance."""
        incoming = tuple(snapshots)
        if not incoming:
            return
        with self.connect() as connection, connection.cursor() as cursor:
            series_ids = tuple({snapshot.series_id for snapshot in incoming})
            for series_id in sorted(series_ids):
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"quote-series:{series_id}",),
                )
            cursor.execute("SELECT series_id FROM quote_series WHERE series_id = ANY(%s)", (list(series_ids),))
            known_series = {row[0] for row in cursor.fetchall()}
            for series_id in series_ids:
                if series_id not in known_series:
                    raise QuoteHistoryConflictError(f"unknown series ID {series_id!r}")

            for snapshot in incoming:
                cursor.execute(
                    "SELECT snapshot_id, series_id, odd, observed_at, captured_at, source "
                    "FROM quote_snapshots WHERE snapshot_id = %s",
                    (snapshot.snapshot_id,),
                )
                existing_by_id = cursor.fetchone()
                if existing_by_id is not None:
                    existing_payload = (existing_by_id[1], existing_by_id[2], existing_by_id[3], existing_by_id[5])
                    incoming_payload = (
                        snapshot.series_id,
                        snapshot.odd,
                        snapshot.observed_at,
                        snapshot.source,
                    )
                    if existing_payload != incoming_payload:
                        raise QuoteHistoryConflictError(
                            "conflicting snapshot ID with different payload"
                        )
                    continue

                cursor.execute(
                    "INSERT INTO quote_snapshots "
                    "(snapshot_id, series_id, odd, observed_at, captured_at, source) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (series_id, observed_at, source) DO NOTHING",
                    (snapshot.snapshot_id, snapshot.series_id, snapshot.odd, snapshot.observed_at, snapshot.captured_at, snapshot.source),
                )
                cursor.execute(
                    "SELECT snapshot_id, series_id, odd, observed_at, captured_at, source "
                    "FROM quote_snapshots "
                    "WHERE series_id = %s AND observed_at = %s AND source = %s",
                    (snapshot.series_id, snapshot.observed_at, snapshot.source),
                )
                row = cursor.fetchone()
                if row is None or (row[1], row[2], row[3], row[5]) != (
                    snapshot.series_id,
                    snapshot.odd,
                    snapshot.observed_at,
                    snapshot.source,
                ):
                    raise QuoteHistoryConflictError(
                        "conflicting observation for semantic quote identity"
                    )

    @staticmethod
    def _require_same_series(row: tuple[Any, ...], series: QuoteSeries) -> None:
        expected = (series.fixture_id, series.bookmaker_id, series.market.value, series.selection.value, series.created_at)
        if tuple(row) != expected:
            raise QuoteHistoryConflictError(f"conflicting definition for series ID {series.series_id!r}")

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

    def complete_market_observation_for_snapshot(
        self, snapshot_id: str
    ) -> PersistedMarketObservation | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT qs.fixture_id, qs.bookmaker_id, qs.market, q.observed_at, q.source "
                "FROM quote_snapshots q JOIN quote_series qs ON qs.series_id = q.series_id "
                "WHERE q.snapshot_id = %s",
                (snapshot_id,),
            )
            context = cursor.fetchone()
            if context is None:
                return None
            cursor.execute(
                "SELECT qs.series_id, q.snapshot_id, qs.fixture_id, qs.bookmaker_id, "
                "qs.market, qs.selection, q.odd, q.observed_at, q.captured_at, q.source "
                "FROM quote_series qs JOIN quote_snapshots q ON q.series_id = qs.series_id "
                "WHERE qs.fixture_id = %s AND qs.bookmaker_id = %s AND qs.market = %s "
                "AND q.observed_at = %s AND q.source = %s "
                "ORDER BY qs.selection, qs.series_id, q.snapshot_id",
                context,
            )
            rows = cursor.fetchall()
        try:
            bookmaker_key = API_FOOTBALL_BOOKMAKERS[context[1]]
        except KeyError as exc:
            raise QuoteHistoryConflictError("unknown durable bookmaker identity") from exc
        quotes = tuple(
            PersistedQuoteObservation(
                series_id=row[0],
                snapshot_id=row[1],
                fixture_id=row[2],
                bookmaker_id=row[3],
                bookmaker_key=bookmaker_key,
                market=Market(row[4]),
                selection=Selection(row[5]),
                odd=row[6],
                observed_at=row[7],
                captured_at=row[8],
                source=row[9],
            )
            for row in rows
        )
        try:
            observation = PersistedMarketObservation(quotes)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise QuoteHistoryConflictError(
                "incomplete or inconsistent market observation"
            ) from exc
        if all(quote.snapshot_id != snapshot_id for quote in observation.quotes):
            raise QuoteHistoryConflictError("selected snapshot is absent from resolved market")
        return observation

    @staticmethod
    def _row_to_snapshot(row: tuple[Any, ...]) -> QuoteSnapshot:
        return QuoteSnapshot(row[0], row[1], row[2], row[3], row[4], row[5])
