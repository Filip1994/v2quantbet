"""PostgreSQL-authoritative operational state for the Task #13 runtime."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from h2h.domain.competition_scope import CompetitionMetadata, classify_phase_i
from h2h.domain.fixture_identity import ProviderFixtureReference, ResolvedFixtureIdentity
from h2h.workers.quote_refresh_schedule import quote_refresh_decision


ConnectionFactory = Callable[[], Any]
LEADER_LOCK_NAME = "quantbet-production-v1"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _bounded_error(error: BaseException) -> tuple[str, str]:
    error_class = type(error).__name__[:100]
    message = " ".join(str(error).split())[:500]
    return error_class, message


@dataclass(frozen=True, slots=True)
class OpportunityFixture:
    fixture_id: str
    identity: ResolvedFixtureIdentity
    league_id: int
    season: int
    kickoff_at: datetime
    last_captured_at: datetime | None


@dataclass(frozen=True, slots=True)
class OpportunitySelection:
    """Observable scheduling result for the persisted Phase I fixture universe."""

    eligible_fixture_count: int
    phase_i_excluded_count: int
    waiting_for_window_count: int
    waiting_for_refresh_count: int
    due_fixtures: tuple[OpportunityFixture, ...]


@dataclass(frozen=True, slots=True)
class WorkerStatus:
    worker_name: str
    last_started_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    next_due_at: datetime | None
    consecutive_failures: int
    cycle_count: int
    success_count: int
    failure_count: int
    last_error_class: str | None
    last_error_message: str | None
    instance_id: str
    updated_at: datetime


class PostgreSQLLeaderLock:
    """Own one session-level advisory lock for the active scheduler."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.acquired = False

    def try_acquire(self) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", (LEADER_LOCK_NAME,))
            self.acquired = bool(cursor.fetchone()[0])
        return self.acquired

    def healthy(self) -> bool:
        if not self.acquired:
            return False
        try:
            with self._connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
        except Exception:  # noqa: BLE001 - any broken session forfeits leadership
            self.acquired = False
            return False

    def close(self) -> None:
        try:
            if self.acquired:
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (LEADER_LOCK_NAME,)
                    )
        finally:
            self.acquired = False
            self._connection.close()


class PostgreSQLRuntimeRepository:
    def __init__(
        self, database_url: str | None = None, *, connect: ConnectionFactory | None = None
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect

    def connect(self) -> Any:
        if self._connect_factory is not None:
            return self._connect_factory()
        import psycopg

        return psycopg.connect(self._database_url)

    def check_database(self) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)

    def verify_schema(self, expected: Iterable[str]) -> tuple[str, ...]:
        expected_set = set(expected)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT version FROM schema_migrations")
            actual = {row[0] for row in cursor.fetchall()}
        missing = tuple(sorted(expected_set - actual))
        if missing:
            raise RuntimeError(f"database schema is missing migrations: {', '.join(missing)}")
        return tuple(sorted(actual))

    def open_leader_lock(self) -> PostgreSQLLeaderLock:
        connection = self.connect()
        connection.autocommit = True
        return PostgreSQLLeaderLock(connection)

    def verify_bankroll(self, account_id: str, currency: str, initial_minor: int) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT a.currency, l.amount_minor FROM bankroll_accounts a "
                "LEFT JOIN bankroll_ledger_entries l ON l.bankroll_account_id = a.bankroll_account_id "
                "AND l.entry_type = 'INITIAL_BANKROLL' WHERE a.bankroll_account_id = %s",
                (account_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("configured bankroll account is not bootstrapped")
            if row != (currency, initial_minor):
                raise RuntimeError("configured bankroll facts conflict with durable state")

    def due_opportunity_fixtures(
        self,
        *,
        bookmaker_id: int,
        allowed_statuses: tuple[str, ...],
        now: datetime,
    ) -> tuple[OpportunityFixture, ...]:
        return self.select_opportunity_fixtures(
            bookmaker_id=bookmaker_id,
            allowed_statuses=allowed_statuses,
            now=now,
        ).due_fixtures

    def select_opportunity_fixtures(
        self,
        *,
        bookmaker_id: int,
        allowed_statuses: tuple[str, ...],
        now: datetime,
    ) -> OpportunitySelection:
        current = _utc(now)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT f.fixture_id, f.provider_fixture_id::bigint, f.league_id, f.season, "
                "latest.kickoff_at, latest.country, latest.competition_name, "
                "latest.competition_type, MAX(q.captured_at) "
                "FROM fixtures f JOIN LATERAL (SELECT kickoff_at, provider_status, country, "
                "competition_name, competition_type "
                "FROM fixture_observations o WHERE o.fixture_id = f.fixture_id "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "LEFT JOIN quote_series s ON s.fixture_id = f.fixture_id AND s.bookmaker_id = %s "
                "LEFT JOIN quote_snapshots q ON q.series_id = s.series_id "
                "WHERE latest.kickoff_at > %s "
                "AND latest.provider_status = ANY(%s) "
                "GROUP BY f.fixture_id, f.provider_fixture_id, f.league_id, f.season, "
                "latest.kickoff_at, latest.country, latest.competition_name, latest.competition_type "
                "ORDER BY latest.kickoff_at, f.fixture_id",
                (bookmaker_id, current, list(allowed_statuses)),
            )
            rows = cursor.fetchall()
        due: list[OpportunityFixture] = []
        eligible = 0
        excluded = 0
        waiting_for_window = 0
        waiting_for_refresh = 0
        for (
            fixture_id,
            provider_id,
            league_id,
            season,
            kickoff_at,
            country,
            competition_name,
            competition_type,
            last_captured,
        ) in rows:
            scope = classify_phase_i(
                CompetitionMetadata(
                    country=country,
                    name=competition_name,
                    type=competition_type,
                    level=None,
                )
            )
            if not scope.eligible:
                excluded += 1
                continue
            eligible += 1
            provider_id = int(provider_id)
            decision = quote_refresh_decision(now=current, kickoff_at=kickoff_at)
            if not decision.eligible or decision.interval is None:
                waiting_for_window += 1
                continue
            if last_captured is not None and last_captured + decision.interval > current:
                waiting_for_refresh += 1
                continue
            due.append(
                OpportunityFixture(
                    fixture_id=fixture_id,
                    identity=ResolvedFixtureIdentity(
                        fixture_id=fixture_id,
                        provider_reference=ProviderFixtureReference(
                            "api-football", str(provider_id)
                        ),
                    ),
                    league_id=int(league_id),
                    season=int(season),
                    kickoff_at=kickoff_at,
                    last_captured_at=last_captured,
                )
            )
        return OpportunitySelection(
            eligible_fixture_count=eligible,
            phase_i_excluded_count=excluded,
            waiting_for_window_count=waiting_for_window,
            waiting_for_refresh_count=waiting_for_refresh,
            due_fixtures=tuple(due),
        )

    def latest_complete_snapshot_ids(
        self, fixture_id: str, bookmaker_id: int
    ) -> tuple[str, ...]:
        """Return both selections for each latest complete market observation."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "WITH ranked AS (SELECT s.market, q.observed_at, q.source, "
                "MAX(q.captured_at) AS captured_at FROM quote_series s "
                "JOIN quote_snapshots q ON q.series_id = s.series_id "
                "WHERE s.fixture_id = %s AND s.bookmaker_id = %s "
                "GROUP BY s.market, q.observed_at, q.source HAVING COUNT(DISTINCT s.selection) = 2), "
                "chosen AS (SELECT DISTINCT ON (market) market, observed_at, source, captured_at "
                "FROM ranked ORDER BY market, observed_at DESC, captured_at DESC, source) "
                "SELECT q.snapshot_id FROM chosen c JOIN quote_series s "
                "ON s.fixture_id = %s AND s.bookmaker_id = %s AND s.market = c.market "
                "JOIN quote_snapshots q ON q.series_id = s.series_id "
                "AND q.observed_at = c.observed_at AND q.source = c.source "
                "ORDER BY s.market, s.selection, q.snapshot_id",
                (fixture_id, bookmaker_id, fixture_id, bookmaker_id),
            )
            return tuple(row[0] for row in cursor.fetchall())

    def item_retry_due(self, worker: str, item_id: str, *, now: datetime) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT next_retry_at <= %s FROM production_item_failures "
                "WHERE worker_name = %s AND item_id = %s",
                (_utc(now), worker, item_id),
            )
            row = cursor.fetchone()
            return row is None or bool(row[0])

    def record_item_failure(
        self, worker: str, item_id: str, error: BaseException, *, failed_at: datetime
    ) -> None:
        error_class, message = _bounded_error(error)
        failed = _utc(failed_at)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO production_item_failures (worker_name, item_id, failure_count, "
                "last_failure_at, next_retry_at, last_error_class, last_error_message) "
                "VALUES (%s, %s, 1, %s, %s, %s, %s) ON CONFLICT (worker_name, item_id) "
                "DO UPDATE SET failure_count = production_item_failures.failure_count + 1, "
                "last_failure_at = EXCLUDED.last_failure_at, next_retry_at = LEAST("
                "EXCLUDED.last_failure_at + interval '1 hour', EXCLUDED.last_failure_at + "
                "(power(2, LEAST(production_item_failures.failure_count, 8)) * interval '5 seconds')), "
                "last_error_class = EXCLUDED.last_error_class, "
                "last_error_message = EXCLUDED.last_error_message",
                (worker, item_id, failed, failed + timedelta(seconds=5), error_class, message),
            )

    def clear_item_failure(self, worker: str, item_id: str) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM production_item_failures WHERE worker_name = %s AND item_id = %s",
                (worker, item_id),
            )

    def worker_started(self, worker: str, instance_id: str, *, at: datetime) -> None:
        current = _utc(at)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO production_worker_status (worker_name, last_started_at, cycle_count, "
                "instance_id, updated_at) VALUES (%s, %s, 1, %s, %s) "
                "ON CONFLICT (worker_name) DO UPDATE SET last_started_at = EXCLUDED.last_started_at, "
                "cycle_count = production_worker_status.cycle_count + 1, "
                "instance_id = EXCLUDED.instance_id, updated_at = EXCLUDED.updated_at",
                (worker, current, instance_id, current),
            )

    def worker_succeeded(
        self, worker: str, instance_id: str, *, at: datetime, next_due_at: datetime
    ) -> None:
        current = _utc(at)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE production_worker_status SET last_success_at = %s, next_due_at = %s, "
                "consecutive_failures = 0, success_count = success_count + 1, "
                "last_error_class = NULL, last_error_message = NULL, instance_id = %s, "
                "updated_at = %s WHERE worker_name = %s",
                (current, _utc(next_due_at), instance_id, current, worker),
            )

    def worker_failed(
        self,
        worker: str,
        instance_id: str,
        error: BaseException,
        *,
        at: datetime,
        next_due_at: datetime,
    ) -> None:
        current = _utc(at)
        error_class, message = _bounded_error(error)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE production_worker_status SET last_failure_at = %s, next_due_at = %s, "
                "consecutive_failures = consecutive_failures + 1, failure_count = failure_count + 1, "
                "last_error_class = %s, last_error_message = %s, instance_id = %s, updated_at = %s "
                "WHERE worker_name = %s",
                (current, _utc(next_due_at), error_class, message, instance_id, current, worker),
            )

    def worker_statuses(self) -> tuple[WorkerStatus, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT worker_name, last_started_at, last_success_at, last_failure_at, next_due_at, "
                "consecutive_failures, cycle_count, success_count, failure_count, last_error_class, "
                "last_error_message, instance_id, updated_at FROM production_worker_status "
                "ORDER BY worker_name"
            )
            return tuple(WorkerStatus(*row) for row in cursor.fetchall())

    def operational_counts(self) -> dict[str, int]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE last_error_class = "
                "'ActiveModelUnavailableError'), COUNT(*) FILTER (WHERE last_error_class IN "
                "('OpportunityOddsUnavailableError', 'TransportError', "
                "'QuoteNormalizationError')) FROM production_item_failures"
            )
            retry, model_unavailable, odds_unavailable = (
                int(value) for value in cursor.fetchone()
            )
            cursor.execute(
                "SELECT COUNT(*) FROM fixture_result_acquisition_states WHERE phase <> 'COMPLETE'"
            )
            pending_results = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT COUNT(*) FROM fixture_result_acquisition_states WHERE correction_required"
            )
            corrections = int(cursor.fetchone()[0])
        return {
            "retry": retry,
            "model_unavailable": model_unavailable,
            "odds_unavailable": odds_unavailable,
            "pending_results": pending_results,
            "correction_required": corrections,
        }
