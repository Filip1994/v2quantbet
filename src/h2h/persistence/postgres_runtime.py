"""PostgreSQL-authoritative operational state for the Task #13 runtime."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from h2h.domain.competition_scope import CompetitionMetadata, classify_phase_i
from h2h.domain.fixture_identity import ProviderFixtureReference, ResolvedFixtureIdentity
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy, quote_refresh_decision


ConnectionFactory = Callable[[], Any]
LEADER_LOCK_NAME = "quantbet-production-v1"

_OPPORTUNITY_NO_ODDS_ERROR = "OpportunityOddsUnavailableError"


def _initial_item_retry_at(worker: str, error_class: str, failed_at: datetime) -> datetime:
    if worker == "opportunity" and error_class == _OPPORTUNITY_NO_ODDS_ERROR:
        return failed_at + timedelta(minutes=10)
    return failed_at + timedelta(seconds=5)


_ITEM_FAILURE_UPSERT_SQL = (
    "INSERT INTO production_item_failures (worker_name, item_id, failure_count, "
    "last_failure_at, next_retry_at, last_error_class, last_error_message) "
    "VALUES (%s, %s, 1, %s, %s, %s, %s) ON CONFLICT (worker_name, item_id) "
    "DO UPDATE SET failure_count = production_item_failures.failure_count + 1, "
    "last_failure_at = EXCLUDED.last_failure_at, next_retry_at = CASE "
    "WHEN EXCLUDED.worker_name = 'opportunity' "
    "AND EXCLUDED.last_error_class = 'OpportunityOddsUnavailableError' THEN LEAST("
    "EXCLUDED.last_failure_at + interval '1 hour', EXCLUDED.last_failure_at + "
    "(power(2, LEAST(production_item_failures.failure_count, 3)) * interval '10 minutes')) "
    "ELSE LEAST(EXCLUDED.last_failure_at + interval '1 hour', EXCLUDED.last_failure_at + "
    "(power(2, LEAST(production_item_failures.failure_count, 8)) * interval '5 seconds')) END, "
    "last_error_class = EXCLUDED.last_error_class, "
    "last_error_message = EXCLUDED.last_error_message"
)


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
    next_retry_at: datetime | None = None
    quote_freshness_state: str | None = None
    stale_quote_attempt_count: int = 0
    stale_quote_next_retry_at: datetime | None = None
    stale_retry: bool = False


@dataclass(frozen=True, slots=True)
class CompleteMarketQuoteState:
    market: str
    observed_at: datetime
    captured_at: datetime
    source: str


@dataclass(frozen=True, slots=True)
class QuoteRefreshState:
    freshness_state: str
    stale_attempt_count: int
    first_stale_at: datetime | None
    last_attempt_at: datetime
    next_retry_at: datetime | None
    latest_observed_at: datetime | None
    latest_captured_at: datetime | None


@dataclass(frozen=True, slots=True)
class OpportunityCursor:
    kickoff_at: datetime
    fixture_id: str


@dataclass(frozen=True, slots=True)
class OpportunitySelection:
    """Observable scheduling result for the persisted Phase I fixture universe."""

    eligible_fixture_count: int
    phase_i_excluded_count: int
    waiting_for_window_count: int
    waiting_for_refresh_count: int
    due_fixtures: tuple[OpportunityFixture, ...]
    continuation: OpportunityCursor | None = None
    has_more: bool = False
    stale_retries_stopped: int = 0


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
            cursor.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", (LEADER_LOCK_NAME,)
            )
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
        maximum_quote_age_seconds: int,
        minimum_time_to_kickoff_seconds: int,
        stale_retry_policy: StaleQuoteRetryPolicy,
    ) -> tuple[OpportunityFixture, ...]:
        return self.select_opportunity_fixtures(
            bookmaker_id=bookmaker_id,
            allowed_statuses=allowed_statuses,
            now=now,
            item_limit=10,
            maximum_quote_age_seconds=maximum_quote_age_seconds,
            minimum_time_to_kickoff_seconds=minimum_time_to_kickoff_seconds,
            stale_retry_policy=stale_retry_policy,
        ).due_fixtures

    def select_opportunity_fixtures(
        self,
        *,
        bookmaker_id: int,
        allowed_statuses: tuple[str, ...],
        now: datetime,
        maximum_quote_age_seconds: int,
        minimum_time_to_kickoff_seconds: int,
        stale_retry_policy: StaleQuoteRetryPolicy,
        item_limit: int = 10,
        after: OpportunityCursor | None = None,
        stale_only: bool = False,
    ) -> OpportunitySelection:
        if item_limit <= 0:
            raise ValueError("item_limit must be positive")
        current = _utc(now)
        # Classification remains application-owned, so scan a bounded multiple of the
        # item budget. Keyset continuation prevents ineligible early rows from pinning
        # every cycle while avoiding an unbounded future-fixture materialisation.
        scan_limit = item_limit * 4
        after_kickoff = None if after is None else _utc(after.kickoff_at)
        after_fixture_id = None if after is None else after.fixture_id
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT f.fixture_id, f.provider_fixture_id::bigint, f.league_id, f.season, "
                "latest.kickoff_at, latest.country, latest.competition_name, "
                "latest.competition_type, captures.last_captured_at, failures.next_retry_at, "
                "refresh.freshness_state, refresh.stale_attempt_count, refresh.next_retry_at, "
                "refresh.last_attempt_at, "
                "complete.latest_observed_at, complete.latest_captured_at "
                "FROM fixtures f JOIN LATERAL (SELECT kickoff_at, provider_status, country, "
                "competition_name, competition_type "
                "FROM fixture_observations o WHERE o.fixture_id = f.fixture_id "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "LEFT JOIN LATERAL (SELECT MAX(q.captured_at) AS last_captured_at "
                "FROM quote_series s JOIN quote_snapshots q ON q.series_id = s.series_id "
                "WHERE s.fixture_id = f.fixture_id AND s.bookmaker_id = %s) captures ON TRUE "
                "LEFT JOIN LATERAL (SELECT MIN(markets.observed_at) AS latest_observed_at, "
                "MAX(markets.captured_at) AS latest_captured_at FROM (SELECT DISTINCT ON (market) "
                "market, observed_at, captured_at FROM (SELECT s.market, q.observed_at, q.source, "
                "MAX(q.captured_at) AS captured_at FROM quote_series s JOIN quote_snapshots q "
                "ON q.series_id = s.series_id WHERE s.fixture_id = f.fixture_id "
                "AND s.bookmaker_id = %s GROUP BY s.market, q.observed_at, q.source "
                "HAVING COUNT(DISTINCT s.selection) = 2) complete_observations "
                "ORDER BY market, observed_at DESC, captured_at DESC, source) markets) complete ON TRUE "
                "LEFT JOIN production_quote_refresh_states refresh ON refresh.fixture_id = "
                "f.fixture_id AND refresh.bookmaker_id = %s "
                "LEFT JOIN production_item_failures failures ON failures.worker_name = "
                "'opportunity' AND failures.item_id = f.fixture_id "
                "JOIN model_coverage_scopes coverage ON coverage.provider = f.provider "
                "AND coverage.team_id_namespace = f.provider "
                "AND coverage.league_id = f.league_id AND coverage.season = f.season "
                "AND coverage.active_model_version_id IS NOT NULL "
                "WHERE latest.kickoff_at > %s "
                "AND latest.kickoff_at <= %s "
                "AND latest.provider_status = ANY(%s) "
                "AND (failures.next_retry_at IS NULL OR failures.next_retry_at <= %s) "
                "AND (%s = FALSE OR (refresh.freshness_state = 'STALE' "
                "AND refresh.next_retry_at IS NOT NULL AND refresh.next_retry_at <= %s)) "
                "AND (%s::timestamptz IS NULL OR (latest.kickoff_at, f.fixture_id) > (%s, %s)) "
                "ORDER BY latest.kickoff_at, f.fixture_id LIMIT %s",
                (
                    bookmaker_id,
                    bookmaker_id,
                    bookmaker_id,
                    current,
                    current + timedelta(hours=72),
                    list(allowed_statuses),
                    current,
                    stale_only,
                    current,
                    after_kickoff,
                    after_kickoff,
                    after_fixture_id,
                    scan_limit + 1,
                ),
            )
            rows = cursor.fetchall()
        due: list[OpportunityFixture] = []
        eligible = 0
        excluded = 0
        waiting_for_window = 0
        waiting_for_refresh = 0
        stale_retries_stopped = 0
        continuation: OpportunityCursor | None = None
        has_more = len(rows) > scan_limit
        for row in rows[:scan_limit]:
            (
                fixture_id,
                provider_id,
                league_id,
                season,
                kickoff_at,
                country,
                competition_name,
                competition_type,
                last_captured,
                next_retry_at,
                freshness_state,
                stale_attempt_count,
                stale_next_retry_at,
                refresh_last_attempt_at,
                latest_complete_observed_at,
                _latest_complete_captured_at,
            ) = row
            continuation = OpportunityCursor(kickoff_at, fixture_id)
            scope = classify_phase_i(
                CompetitionMetadata(
                    country=country,
                    name=competition_name,
                    type=competition_type,
                    level=None,
                    league_id=int(league_id),
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
            derived_stale = bool(
                freshness_state is None
                and latest_complete_observed_at is not None
                and current - latest_complete_observed_at
                > timedelta(seconds=maximum_quote_age_seconds)
            )
            persisted_stale = freshness_state == "STALE"
            scheduling_anchor = last_captured
            if refresh_last_attempt_at is not None and (
                scheduling_anchor is None or refresh_last_attempt_at > scheduling_anchor
            ):
                scheduling_anchor = refresh_last_attempt_at
            stale_retry = False
            if derived_stale or persisted_stale:
                if kickoff_at - current <= timedelta(seconds=minimum_time_to_kickoff_seconds):
                    waiting_for_window += 1
                    stale_retries_stopped += 1
                    continue
                if persisted_stale:
                    if stale_next_retry_at is not None:
                        if stale_next_retry_at > current:
                            waiting_for_refresh += 1
                            continue
                        stale_retry = True
                    elif scheduling_anchor is not None and (
                        scheduling_anchor + decision.interval > current
                    ):
                        # The accelerated path has reached its explicit bound. Normal
                        # cadence remains available without creating a tight loop.
                        waiting_for_refresh += 1
                        continue
                else:
                    # A pre-existing stale complete observation has no retry row yet
                    # (for example immediately after migration). Do not let its recent
                    # transport capture suppress the first stale-aware pull.
                    stale_retry = True
            elif scheduling_anchor is not None and scheduling_anchor + decision.interval > current:
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
                    next_retry_at=next_retry_at,
                    quote_freshness_state=freshness_state,
                    stale_quote_attempt_count=int(stale_attempt_count or 0),
                    stale_quote_next_retry_at=stale_next_retry_at,
                    stale_retry=stale_retry,
                )
            )
            if len(due) >= item_limit:
                has_more = True
                break
        if not has_more:
            continuation = None
        return OpportunitySelection(
            eligible_fixture_count=eligible,
            phase_i_excluded_count=excluded,
            waiting_for_window_count=waiting_for_window,
            waiting_for_refresh_count=waiting_for_refresh,
            due_fixtures=tuple(due),
            continuation=continuation,
            has_more=has_more,
            stale_retries_stopped=stale_retries_stopped,
        )

    def select_due_stale_quote_retries(
        self,
        *,
        bookmaker_id: int,
        allowed_statuses: tuple[str, ...],
        now: datetime,
        maximum_quote_age_seconds: int,
        minimum_time_to_kickoff_seconds: int,
        stale_retry_policy: StaleQuoteRetryPolicy,
        item_limit: int = 1,
    ) -> OpportunitySelection:
        """Reserve a bounded slot for due stale retries independently of the normal cursor."""
        return self.select_opportunity_fixtures(
            bookmaker_id=bookmaker_id,
            allowed_statuses=allowed_statuses,
            now=now,
            maximum_quote_age_seconds=maximum_quote_age_seconds,
            minimum_time_to_kickoff_seconds=minimum_time_to_kickoff_seconds,
            stale_retry_policy=stale_retry_policy,
            item_limit=item_limit,
            stale_only=True,
        )

    def latest_complete_market_states(
        self, fixture_id: str, bookmaker_id: int
    ) -> tuple[CompleteMarketQuoteState, ...]:
        """Return one exact, latest two-way observation per supported market."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "WITH complete AS (SELECT s.market, q.observed_at, q.source, "
                "MAX(q.captured_at) AS captured_at FROM quote_series s "
                "JOIN quote_snapshots q ON q.series_id = s.series_id "
                "WHERE s.fixture_id = %s AND s.bookmaker_id = %s "
                "GROUP BY s.market, q.observed_at, q.source "
                "HAVING COUNT(DISTINCT s.selection) = 2) "
                "SELECT DISTINCT ON (market) market, observed_at, captured_at, source "
                "FROM complete ORDER BY market, observed_at DESC, captured_at DESC, source",
                (fixture_id, bookmaker_id),
            )
            return tuple(CompleteMarketQuoteState(*row) for row in cursor.fetchall())

    def record_quote_refresh_state(
        self,
        fixture_id: str,
        bookmaker_id: int,
        *,
        freshness_state: str,
        attempted_at: datetime,
        latest_observed_at: datetime | None,
        latest_captured_at: datetime | None,
        stale_retry_policy: StaleQuoteRetryPolicy,
    ) -> QuoteRefreshState:
        """Persist freshness separately from generic transport/item failures."""
        if freshness_state not in {
            "FRESH",
            "USABLE_STALE",
            "STALE",
            "NO_USABLE_QUOTE",
        }: