"""Durable exposure-blocked research signals and bankroll-free quote monitoring."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from h2h.domain.fixture_identity import ProviderFixtureReference, ResolvedFixtureIdentity
from h2h.domain.odds import Market
from h2h.domain.pick_monitoring import (
    ClosingFinalization,
    ClosingOutcome,
    MonitoringRecord,
    MonitoringState,
    OddsLifecyclePolicy,
)
from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.persistence.pick_monitoring import (
    PickClosingNotDueError,
    PickMonitoringConflictError,
    PickMonitoringNotStartedError,
    PickQuoteRefreshTarget,
)


ConnectionFactory = Callable[[], Any]


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _fact_id(prefix: str, value: str) -> str:
    return f"{prefix}:" + sha256(value.encode("utf-8")).hexdigest()


class PostgreSQLResearchSignalRepository:
    """Persist exposure-only candidates and track their same-book quote lifecycle."""

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
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg[binary]") from exc
        return psycopg.connect(self._database_url)

    @staticmethod
    def _lock(cursor: Any, value: str) -> None:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (value,))

    def record_exposure_blocked(
        self,
        evaluation_id: str,
        policy: RegistrationPolicyConfig,
        *,
        detected_at: datetime,
    ) -> str:
        detected = _utc(detected_at, "detected_at")
        if not isinstance(policy, RegistrationPolicyConfig):
            raise TypeError("policy must be a RegistrationPolicyConfig")
        signal_id = _fact_id("research-signal-v1", evaluation_id)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id FROM value_evaluations WHERE evaluation_id = %s",
                (evaluation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"value evaluation {evaluation_id!r} does not exist")
            fixture_id = str(row[0])
            cursor.execute(
                "INSERT INTO research_signals "
                "(signal_id, evaluation_id, fixture_id, blocked_reason, "
                "registration_policy_fingerprint, allowed_fixture_statuses, "
                "maximum_quote_age_seconds, detected_at) "
                "VALUES (%s, %s, %s, 'MAX_OPEN_EXPOSURE_EXCEEDED', %s, %s, %s, %s) "
                "ON CONFLICT (evaluation_id) DO NOTHING",
                (
                    signal_id,
                    evaluation_id,
                    fixture_id,
                    policy.fingerprint,
                    list(policy.allowed_fixture_statuses),
                    policy.maximum_quote_age_seconds,
                    detected,
                ),
            )
            cursor.execute(
                "SELECT signal_id, fixture_id, registration_policy_fingerprint, "
                "allowed_fixture_statuses, maximum_quote_age_seconds "
                "FROM research_signals WHERE evaluation_id = %s",
                (evaluation_id,),
            )
            stored = cursor.fetchone()
            expected = (
                signal_id,
                fixture_id,
                policy.fingerprint,
                list(policy.allowed_fixture_statuses),
                policy.maximum_quote_age_seconds,
            )
            if stored is None:
                raise RuntimeError("research signal insert disappeared")
            actual = (stored[0], stored[1], stored[2], list(stored[3]), int(stored[4]))
            if actual != expected:
                raise PickMonitoringConflictError("research signal replay changed provenance")
            return signal_id

    def start(
        self, signal_id: str, policy: OddsLifecyclePolicy, *, started_at: datetime
    ) -> MonitoringRecord:
        started = _utc(started_at, "started_at")
        if not isinstance(policy, OddsLifecyclePolicy):
            raise TypeError("policy must be an OddsLifecyclePolicy")
        with self.connect() as connection, connection.cursor() as cursor:
            self._lock(cursor, f"research-monitoring:{signal_id}")
            context = self._require_context(cursor, signal_id)
            cursor.execute(
                "SELECT kickoff_at FROM fixture_observations WHERE fixture_id = %s "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
                (context[1],),
            )
            fixture = cursor.fetchone()
            if fixture is None:
                raise PickMonitoringConflictError("no authoritative fixture observation")
            lead_seconds = max(900, policy.closing_max_age_seconds * 3)
            next_refresh = max(started, fixture[0] - timedelta(seconds=lead_seconds))
            existing = self._load_state(cursor, signal_id)
            if existing is not None:
                if existing.policy != policy:
                    raise PickMonitoringConflictError(
                        "research monitoring replay used different lifecycle configuration"
                    )
                if existing.state is MonitoringState.CLOSED_FOR_ODDS:
                    raise PickMonitoringConflictError(
                        "closed research signal cannot return to MONITORING"
                    )
                return existing
            cursor.execute(
                "INSERT INTO research_signal_monitoring_states "
                "(signal_id, state, lifecycle_policy_version, monitoring_interval_seconds, "
                "current_max_age_seconds, closing_max_age_seconds, started_at, next_refresh_at, "
                "updated_at, version) VALUES (%s, 'MONITORING', %s, %s, %s, %s, %s, %s, %s, 1)",
                (
                    signal_id,
                    policy.version,
                    policy.monitoring_interval_seconds,
                    policy.current_max_age_seconds,
                    policy.closing_max_age_seconds,
                    started,
                    next_refresh,
                    started,
                ),
            )
            return self._load_state(cursor, signal_id, required=True)

    def claim_due(self, *, claimed_at: datetime, limit: int) -> tuple[str, ...]:
        """Claim at most one representative per selected quote series.

        Multiple blocked evaluations can share one fixture/bookmaker/market/selection series.
        Advancing every state on that series makes one provider refresh serve all of them.
        """
        claimed = _utc(claimed_at, "claimed_at")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT signal_id, selected_series_id, monitoring_interval_seconds FROM ("
                "SELECT DISTINCT ON (e.selected_series_id) "
                "m.signal_id, e.selected_series_id, m.monitoring_interval_seconds, "
                "m.next_refresh_at "
                "FROM research_signal_monitoring_states m "
                "JOIN research_signals s ON s.signal_id = m.signal_id "
                "JOIN value_evaluations e ON e.evaluation_id = s.evaluation_id "
                "WHERE m.state = 'MONITORING' AND m.next_refresh_at <= %s "
                "ORDER BY e.selected_series_id, m.next_refresh_at, m.signal_id"
                ") due ORDER BY next_refresh_at, signal_id LIMIT %s",
                (claimed, limit),
            )
            rows = cursor.fetchall()
            for _signal_id, series_id, interval in rows:
                cursor.execute(
                    "UPDATE research_signal_monitoring_states m SET "
                    "next_refresh_at = %s, updated_at = %s, version = version + 1 "
                    "FROM research_signals s, value_evaluations e "
                    "WHERE m.signal_id = s.signal_id "
                    "AND e.evaluation_id = s.evaluation_id "
                    "AND e.selected_series_id = %s "
                    "AND m.state = 'MONITORING' AND m.next_refresh_at <= %s",
                    (
                        claimed + timedelta(seconds=int(interval)),
                        claimed,
                        series_id,
                        claimed,
                    ),
                )
            return tuple(str(row[0]) for row in rows)

    def has_due_refreshes(self, *, as_of: datetime) -> bool:
        current = _utc(as_of, "as_of")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM research_signal_monitoring_states "
                "WHERE state = 'MONITORING' AND next_refresh_at <= %s)",
                (current,),
            )
            return bool(cursor.fetchone()[0])

    def unstarted_pick_ids(self) -> tuple[str, ...]:
        """Compatibility with the generic monitoring reconciler."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT s.signal_id FROM research_signals s "
                "LEFT JOIN research_signal_monitoring_states m ON m.signal_id = s.signal_id "
                "WHERE m.signal_id IS NULL ORDER BY s.detected_at, s.signal_id"
            )
            return tuple(str(row[0]) for row in cursor.fetchall())

    def monitored_pick_ids(self) -> tuple[str, ...]:
        """Compatibility with the generic monitoring reconciler."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT signal_id FROM research_signal_monitoring_states "
                "WHERE state = 'MONITORING' ORDER BY started_at, signal_id"
            )
            return tuple(str(row[0]) for row in cursor.fetchall())

    def quote_refresh_targets_for_picks(
        self, signal_ids: tuple[str, ...]
    ) -> tuple[PickQuoteRefreshTarget, ...]:
        """Return distinct exact-bookmaker/market targets for claimed research signals."""
        if not signal_ids:
            return ()
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT f.fixture_id, f.provider, f.provider_fixture_id, "
                "e.bookmaker_id, e.market "
                "FROM research_signals s "
                "JOIN value_evaluations e ON e.evaluation_id = s.evaluation_id "
                "JOIN fixtures f ON f.fixture_id = s.fixture_id "
                "JOIN research_signal_monitoring_states m ON m.signal_id = s.signal_id "
                "WHERE s.signal_id = ANY(%s) AND m.state = 'MONITORING' "
                "ORDER BY f.fixture_id, e.bookmaker_id, e.market",
                (list(signal_ids),),
            )
            return tuple(
                PickQuoteRefreshTarget(
                    ResolvedFixtureIdentity(
                        fixture_id=str(row[0]),
                        provider_reference=ProviderFixtureReference(str(row[1]), str(row[2])),
                    ),
                    int(row[3]),
                    Market(row[4]),
                )
                for row in cursor.fetchall()
            )

    def finalize(self, signal_id: str, *, finalized_at: datetime) -> ClosingFinalization:
        finalized = _utc(finalized_at, "finalized_at")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT signal_id FROM research_signal_monitoring_states "
                "WHERE signal_id = %s FOR UPDATE",
                (signal_id,),
            )
            if cursor.fetchone() is None:
                raise PickMonitoringNotStartedError("research signal monitoring has not started")
            existing = self._load_finalization(cursor, signal_id)
            if existing is not None:
                return existing
            state = self._load_state(cursor, signal_id, required=True)
            if state.state is not MonitoringState.MONITORING:
                raise PickMonitoringConflictError("only MONITORING research signals can close")
            context = self._require_context(cursor, signal_id)
            cursor.execute(
                "SELECT fixture_observation_id, kickoff_at FROM fixture_observations "
                "WHERE fixture_id = %s AND observed_at <= %s AND persisted_at <= %s "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
                (context[1], finalized, finalized),
            )
            fixture = cursor.fetchone()
            if fixture is None:
                raise PickMonitoringConflictError("no authoritative fixture observation")
            fixture_observation_id, cutoff_at = fixture
            if finalized < cutoff_at:
                raise PickClosingNotDueError("authoritative kickoff cutoff has not passed")

            candidate = self._candidate(
                cursor,
                fixture_id=context[1],
                series_id=context[2],
                source=context[3],
                cutoff_at=cutoff_at,
                allowed_statuses=context[4],
            )
            if candidate is None:
                outcome = ClosingOutcome.NO_VALID_QUOTE
                candidate_id = closing_id = None
            else:
                candidate_id = str(candidate[0])
                age = cutoff_at - candidate[3]
                if timedelta(0) <= age <= timedelta(seconds=state.policy.closing_max_age_seconds):
                    outcome = ClosingOutcome.CAPTURED
                    closing_id = candidate_id
                else:
                    outcome = ClosingOutcome.STALE_QUOTE
                    closing_id = None

            finalization_id = _fact_id("research-closing-finalization-v1", signal_id)
            cursor.execute(
                "INSERT INTO research_signal_closing_finalizations "
                "(finalization_id, signal_id, fixture_id, fixture_observation_id, cutoff_at, "
                "series_id, source, finalized_at, outcome, candidate_snapshot_id, "
                "closing_snapshot_id, lifecycle_policy_version, closing_max_age_seconds) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    finalization_id,
                    signal_id,
                    context[1],
                    fixture_observation_id,
                    cutoff_at,
                    context[2],
                    context[3],
                    finalized,
                    outcome.value,
                    candidate_id,
                    closing_id,
                    state.policy.version,
                    state.policy.closing_max_age_seconds,
                ),
            )
            cursor.execute(
                "UPDATE research_signal_monitoring_states SET state = 'CLOSED_FOR_ODDS', "
                "next_refresh_at = NULL, updated_at = %s, version = version + 1 "
                "WHERE signal_id = %s AND state = 'MONITORING' AND version = %s",
                (finalized, signal_id, state.version),
            )
            if cursor.rowcount != 1:
                raise PickMonitoringConflictError("research monitoring state CAS failed")
            return self._load_finalization(cursor, signal_id, required=True)

    @staticmethod
    def _require_context(cursor: Any, signal_id: str) -> tuple[Any, ...]:
        cursor.execute(
            "SELECT s.signal_id, s.fixture_id, e.selected_series_id, e.source, "
            "s.allowed_fixture_statuses, e.selected_snapshot_id, s.maximum_quote_age_seconds "
            "FROM research_signals s "
            "JOIN value_evaluations e ON e.evaluation_id = s.evaluation_id "
            "JOIN quote_series q ON q.series_id = e.selected_series_id "
            "AND q.fixture_id = s.fixture_id AND q.bookmaker_id = e.bookmaker_id "
            "AND q.market = e.market AND q.selection = e.selected_selection "
            "WHERE s.signal_id = %s AND e.selected_snapshot_id IS NOT NULL",
            (signal_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError(f"research signal {signal_id!r} does not resolve")
        return (*row[:4], tuple(row[4]), *row[5:])

    @staticmethod
    def _candidate(
        cursor: Any,
        *,
        fixture_id: str,
        series_id: str,
        source: str,
        cutoff_at: datetime,
        allowed_statuses: tuple[str, ...],
    ) -> tuple[Any, ...] | None:
        cursor.execute(
            "SELECT q.snapshot_id, q.series_id, q.odd, q.observed_at, q.captured_at, q.source "
            "FROM quote_snapshots q JOIN LATERAL ("
            "SELECT f.kickoff_at, f.provider_status FROM fixture_observations f "
            "WHERE f.fixture_id = %s AND f.observed_at <= q.captured_at "
            "AND f.persisted_at <= q.captured_at "
            "ORDER BY f.observed_at DESC, f.fixture_observation_id DESC LIMIT 1"
            ") observed_fixture ON TRUE "
            "WHERE q.series_id = %s AND q.source = %s "
            "AND q.observed_at < %s AND q.captured_at < %s "
            "AND observed_fixture.provider_status = ANY(%s) "
            "AND q.observed_at < observed_fixture.kickoff_at "
            "AND q.captured_at < observed_fixture.kickoff_at "
            "ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC LIMIT 1",
            (fixture_id, series_id, source, cutoff_at, cutoff_at, list(allowed_statuses)),
        )
        return cursor.fetchone()

    @staticmethod
    def _row_state(row: tuple[Any, ...]) -> MonitoringRecord:
        return MonitoringRecord(
            pick_id=str(row[0]),
            state=MonitoringState(row[1]),
            policy=OddsLifecyclePolicy(int(row[3]), int(row[4]), int(row[5]), row[2]),
            started_at=row[6],
            next_refresh_at=row[7],
            updated_at=row[8],
            version=int(row[9]),
        )

    def _load_state(
        self, cursor: Any, signal_id: str, *, required: bool = False
    ) -> MonitoringRecord | None:
        cursor.execute(
            "SELECT signal_id, state, lifecycle_policy_version, monitoring_interval_seconds, "
            "current_max_age_seconds, closing_max_age_seconds, started_at, next_refresh_at, "
            "updated_at, version FROM research_signal_monitoring_states WHERE signal_id = %s",
            (signal_id,),
        )
        row = cursor.fetchone()
        if row is None and required:
            raise PickMonitoringConflictError("research monitoring state disappeared")
        return None if row is None else self._row_state(row)

    @staticmethod
    def _row_finalization(row: tuple[Any, ...]) -> ClosingFinalization:
        return ClosingFinalization(
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            ClosingOutcome(row[8]),
            row[9],
            row[10],
            row[11],
            int(row[12]),
        )

    def _load_finalization(
        self, cursor: Any, signal_id: str, *, required: bool = False
    ) -> ClosingFinalization | None:
        cursor.execute(
            "SELECT finalization_id, signal_id, fixture_id, fixture_observation_id, cutoff_at, "
            "series_id, source, finalized_at, outcome, candidate_snapshot_id, "
            "closing_snapshot_id, lifecycle_policy_version, closing_max_age_seconds "
            "FROM research_signal_closing_finalizations WHERE signal_id = %s",
            (signal_id,),
        )
        row = cursor.fetchone()
        if row is None and required:
            raise PickMonitoringConflictError("research closing finalization disappeared")
        return None if row is None else self._row_finalization(row)
