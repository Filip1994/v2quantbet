"""PostgreSQL state, finalization, and read queries for registered-pick monitoring."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from h2h.domain.pick_monitoring import (
    ClosingFinalization,
    ClosingOutcome,
    MonitoringRecord,
    MonitoringState,
    OddsCheckpoint,
    OddsLifecyclePolicy,
    PickOddsLifecycle,
    QuoteFreshness,
)
from h2h.domain.fixture_identity import ProviderFixtureReference, ResolvedFixtureIdentity
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


class PostgreSQLPickMonitoringRepository:
    """One transactional boundary for monitoring state and immutable Closing."""

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

    def start(
        self, pick_id: str, policy: OddsLifecyclePolicy, *, started_at: datetime
    ) -> MonitoringRecord:
        started = _utc(started_at, "started_at")
        if not isinstance(policy, OddsLifecyclePolicy):
            raise TypeError("policy must be an OddsLifecyclePolicy")
        with self.connect() as connection, connection.cursor() as cursor:
            self._lock(cursor, f"pick-monitoring:{pick_id}")
            self._require_context(cursor, pick_id)
            existing = self._load_state(cursor, pick_id)
            if existing is not None:
                if existing.policy != policy:
                    raise PickMonitoringConflictError(
                        "monitoring replay used different pinned lifecycle configuration"
                    )
                if existing.state is MonitoringState.CLOSED_FOR_ODDS:
                    raise PickMonitoringConflictError("closed pick cannot return to MONITORING")
                return existing
            next_refresh = started
            cursor.execute(
                "INSERT INTO pick_monitoring_states "
                "(pick_id, state, lifecycle_policy_version, monitoring_interval_seconds, "
                "current_max_age_seconds, closing_max_age_seconds, started_at, next_refresh_at, "
                "updated_at, version) VALUES (%s, 'MONITORING', %s, %s, %s, %s, %s, %s, %s, 1)",
                (
                    pick_id,
                    policy.version,
                    policy.monitoring_interval_seconds,
                    policy.current_max_age_seconds,
                    policy.closing_max_age_seconds,
                    started,
                    next_refresh,
                    started,
                ),
            )
            cursor.execute(
                "INSERT INTO pick_monitoring_transitions "
                "(transition_id, pick_id, transition_type, from_state, to_state, occurred_at) "
                "VALUES (%s, %s, 'MONITORING_STARTED', 'REGISTERED', 'MONITORING', %s)",
                (
                    _fact_id("pick-monitoring-transition-v1", f"{pick_id}:MONITORING_STARTED"),
                    pick_id,
                    started,
                ),
            )
            return self._load_state(cursor, pick_id, required=True)

    def claim_due(self, *, claimed_at: datetime, limit: int) -> tuple[str, ...]:
        claimed = _utc(claimed_at, "claimed_at")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id, monitoring_interval_seconds FROM pick_monitoring_states "
                "WHERE state = 'MONITORING' AND next_refresh_at <= %s "
                "ORDER BY next_refresh_at, pick_id FOR UPDATE SKIP LOCKED LIMIT %s",
                (claimed, limit),
            )
            rows = cursor.fetchall()
            for pick_id, interval in rows:
                cursor.execute(
                    "UPDATE pick_monitoring_states SET next_refresh_at = %s, updated_at = %s, "
                    "version = version + 1 WHERE pick_id = %s AND state = 'MONITORING'",
                    (claimed + timedelta(seconds=int(interval)), claimed, pick_id),
                )
            return tuple(row[0] for row in rows)

    def finalize(self, pick_id: str, *, finalized_at: datetime) -> ClosingFinalization:
        finalized = _utc(finalized_at, "finalized_at")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id FROM pick_monitoring_states WHERE pick_id = %s FOR UPDATE",
                (pick_id,),
            )
            if cursor.fetchone() is None:
                raise PickMonitoringNotStartedError("pick monitoring has not started")
            existing = self._load_finalization(cursor, pick_id)
            if existing is not None:
                return existing
            state = self._load_state(cursor, pick_id, required=True)
            if state.state is not MonitoringState.MONITORING:
                raise PickMonitoringConflictError("only MONITORING can close for odds")
            context = self._require_context(cursor, pick_id)
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

            series_id, source = context[2], context[3]
            self._lock(cursor, f"quote-series:{series_id}")
            candidate = self._candidate(
                cursor,
                fixture_id=context[1],
                series_id=series_id,
                source=source,
                cutoff_at=cutoff_at,
                allowed_statuses=context[4],
                order="latest",
            )
            if candidate is None:
                outcome = ClosingOutcome.NO_VALID_QUOTE
                candidate_id = closing_id = None
            else:
                candidate_id = candidate.snapshot_id
                if candidate.is_fresh_at(cutoff_at, state.policy.closing_max_age_seconds):
                    outcome = ClosingOutcome.CAPTURED
                    closing_id = candidate_id
                else:
                    outcome = ClosingOutcome.STALE_QUOTE
                    closing_id = None
            finalization_id = _fact_id("pick-closing-finalization-v1", pick_id)
            cursor.execute(
                "INSERT INTO pick_closing_finalizations "
                "(finalization_id, pick_id, fixture_id, fixture_observation_id, cutoff_at, "
                "series_id, source, finalized_at, outcome, candidate_snapshot_id, "
                "closing_snapshot_id, lifecycle_policy_version, closing_max_age_seconds) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    finalization_id,
                    pick_id,
                    context[1],
                    fixture_observation_id,
                    cutoff_at,
                    series_id,
                    source,
                    finalized,
                    outcome.value,
                    candidate_id,
                    closing_id,
                    state.policy.version,
                    state.policy.closing_max_age_seconds,
                ),
            )
            cursor.execute(
                "INSERT INTO pick_monitoring_transitions "
                "(transition_id, pick_id, transition_type, from_state, to_state, occurred_at) "
                "VALUES (%s, %s, 'ODDS_CLOSED', 'MONITORING', 'CLOSED_FOR_ODDS', %s)",
                (
                    _fact_id("pick-monitoring-transition-v1", f"{pick_id}:ODDS_CLOSED"),
                    pick_id,
                    finalized,
                ),
            )
            cursor.execute(
                "UPDATE pick_monitoring_states SET state = 'CLOSED_FOR_ODDS', "
                "next_refresh_at = NULL, updated_at = %s, version = version + 1 "
                "WHERE pick_id = %s AND state = 'MONITORING' AND version = %s",
                (finalized, pick_id, state.version),
            )
            if cursor.rowcount != 1:
                raise PickMonitoringConflictError("monitoring state CAS failed")
            return self._load_finalization(cursor, pick_id, required=True)

    def read_lifecycle(self, pick_id: str, *, as_of: datetime) -> PickOddsLifecycle:
        read_at = _utc(as_of, "as_of")
        with self.connect() as connection, connection.cursor() as cursor:
            context = self._require_context(cursor, pick_id)
            state_record = self._load_state(cursor, pick_id)
            state = MonitoringState.REGISTERED if state_record is None else state_record.state
            finalization = self._load_finalization(cursor, pick_id)
            if finalization is not None:
                cutoff = finalization.cutoff_at
                reference = cutoff
            else:
                cursor.execute(
                    "SELECT kickoff_at FROM fixture_observations WHERE fixture_id = %s "
                    "AND observed_at <= %s AND persisted_at <= %s "
                    "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
                    (context[1], read_at, read_at),
                )
                fixture = cursor.fetchone()
                if fixture is None:
                    raise PickMonitoringConflictError("no authoritative fixture observation")
                cutoff = fixture[0]
                reference = min(read_at, cutoff)

            opening = self._candidate(
                cursor,
                fixture_id=context[1],
                series_id=context[2],
                source=context[3],
                cutoff_at=cutoff,
                allowed_statuses=context[4],
                order="opening",
                available_at=read_at if finalization is None else cutoff,
            )
            current = (
                self._candidate(
                    cursor,
                    fixture_id=context[1],
                    series_id=context[2],
                    source=context[3],
                    cutoff_at=cutoff,
                    allowed_statuses=context[4],
                    order="latest",
                    available_at=read_at,
                )
                if finalization is None
                else (
                    None
                    if finalization.candidate_snapshot_id is None
                    else self._checkpoint_by_id(
                        cursor, finalization.candidate_snapshot_id, required=True
                    )
                )
            )
            entry = self._checkpoint_by_id(cursor, context[5], required=True)
            maximum = (
                state_record.policy.current_max_age_seconds
                if state_record is not None
                else context[6]
            )
            if current is not None:
                current = OddsCheckpoint(
                    current.snapshot_id,
                    current.series_id,
                    current.odd,
                    current.observed_at,
                    current.captured_at,
                    current.source,
                    QuoteFreshness.FRESH
                    if current.is_fresh_at(reference, maximum)
                    else QuoteFreshness.STALE,
                )
            closing = (
                None
                if finalization is None or finalization.closing_snapshot_id is None
                else self._checkpoint_by_id(cursor, finalization.closing_snapshot_id, required=True)
            )
            history = self._history(
                cursor,
                fixture_id=context[1],
                series_id=context[2],
                source=context[3],
                cutoff_at=cutoff,
                allowed_statuses=context[4],
                available_at=read_at if finalization is None else cutoff,
            )
            marker_map: dict[str, list[str]] = {}
            for marker, checkpoint in (
                ("OPEN", opening),
                ("ENTRY", entry),
                ("CURRENT", current),
                ("CLOSE", closing),
            ):
                if checkpoint is not None:
                    marker_map.setdefault(checkpoint.snapshot_id, []).append(marker)
            return PickOddsLifecycle(
                pick_id,
                state,
                opening,
                entry,
                current,
                closing,
                None if finalization is None else finalization.outcome,
                history,
                {key: tuple(value) for key, value in marker_map.items()},
            )

    def unstarted_pick_ids(self) -> tuple[str, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.pick_id FROM registered_picks r LEFT JOIN pick_monitoring_states m "
                "ON m.pick_id = r.pick_id WHERE m.pick_id IS NULL "
                "ORDER BY r.registered_at, r.pick_id"
            )
            return tuple(row[0] for row in cursor.fetchall())

    def monitored_pick_ids(self) -> tuple[str, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id FROM pick_monitoring_states WHERE state = 'MONITORING' "
                "ORDER BY started_at, pick_id"
            )
            return tuple(row[0] for row in cursor.fetchall())

    def fixture_identities_for_picks(
        self, pick_ids: tuple[str, ...]
    ) -> tuple[ResolvedFixtureIdentity, ...]:
        if not pick_ids:
            return ()
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT f.fixture_id, f.provider, f.provider_fixture_id "
                "FROM registered_picks r JOIN fixtures f ON f.fixture_id = r.fixture_id "
                "JOIN pick_monitoring_states m ON m.pick_id = r.pick_id "
                "WHERE r.pick_id = ANY(%s) AND m.state = 'MONITORING' "
                "ORDER BY f.fixture_id",
                (list(pick_ids),),
            )
            return tuple(
                ResolvedFixtureIdentity(
                    fixture_id=row[0],
                    provider_reference=ProviderFixtureReference(row[1], row[2]),
                )
                for row in cursor.fetchall()
            )

    def quote_refresh_targets_for_picks(
        self, pick_ids: tuple[str, ...]
    ) -> tuple[PickQuoteRefreshTarget, ...]:
        """Return one same-bookmaker refresh target per registered pick context."""
        if not pick_ids:
            return ()
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT f.fixture_id, f.provider, f.provider_fixture_id, "
                "e.bookmaker_id FROM registered_picks r "
                "JOIN fixtures f ON f.fixture_id = r.fixture_id "
                "JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id "
                "JOIN pick_monitoring_states m ON m.pick_id = r.pick_id "
                "WHERE r.pick_id = ANY(%s) AND m.state = 'MONITORING' "
                "ORDER BY f.fixture_id, e.bookmaker_id",
                (list(pick_ids),),
            )
            return tuple(
                PickQuoteRefreshTarget(
                    ResolvedFixtureIdentity(
                        fixture_id=row[0],
                        provider_reference=ProviderFixtureReference(row[1], row[2]),
                    ),
                    int(row[3]),
                )
                for row in cursor.fetchall()
            )

    @staticmethod
    def _require_context(cursor: Any, pick_id: str) -> tuple[Any, ...]:
        cursor.execute(
            "SELECT r.pick_id, r.fixture_id, e.selected_series_id, e.source, "
            "c.configuration->'allowed_fixture_statuses', r.entry_snapshot_id, "
            "(c.configuration->>'maximum_quote_age_seconds')::integer "
            "FROM registered_picks r JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id "
            "JOIN pick_policy_configurations c ON c.config_fingerprint = r.config_fingerprint "
            "WHERE r.pick_id = %s AND r.entry_snapshot_id = e.selected_snapshot_id",
            (pick_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError(f"registered pick {pick_id!r} does not exist or has invalid Entry")
        statuses = row[4]
        if isinstance(statuses, str):
            import json

            statuses = json.loads(statuses)
        return (*row[:4], tuple(statuses), *row[5:])

    @staticmethod
    def _row_state(row: tuple[Any, ...]) -> MonitoringRecord:
        return MonitoringRecord(
            pick_id=row[0],
            state=MonitoringState(row[1]),
            policy=OddsLifecyclePolicy(int(row[3]), int(row[4]), int(row[5]), row[2]),
            started_at=row[6],
            next_refresh_at=row[7],
            updated_at=row[8],
            version=int(row[9]),
        )

    def _load_state(
        self, cursor: Any, pick_id: str, *, required: bool = False
    ) -> MonitoringRecord | None:
        cursor.execute(
            "SELECT pick_id, state, lifecycle_policy_version, monitoring_interval_seconds, "
            "current_max_age_seconds, closing_max_age_seconds, started_at, next_refresh_at, "
            "updated_at, version FROM pick_monitoring_states WHERE pick_id = %s",
            (pick_id,),
        )
        row = cursor.fetchone()
        if row is None and required:
            raise PickMonitoringConflictError("monitoring state disappeared")
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
        self, cursor: Any, pick_id: str, *, required: bool = False
    ) -> ClosingFinalization | None:
        cursor.execute(
            "SELECT finalization_id, pick_id, fixture_id, fixture_observation_id, cutoff_at, "
            "series_id, source, finalized_at, outcome, candidate_snapshot_id, "
            "closing_snapshot_id, lifecycle_policy_version, closing_max_age_seconds "
            "FROM pick_closing_finalizations WHERE pick_id = %s",
            (pick_id,),
        )
        row = cursor.fetchone()
        if row is None and required:
            raise PickMonitoringConflictError("closing finalization disappeared")
        return None if row is None else self._row_finalization(row)

    @staticmethod
    def _checkpoint(row: tuple[Any, ...]) -> OddsCheckpoint:
        return OddsCheckpoint(row[0], row[1], float(row[2]), row[3], row[4], row[5])

    def _checkpoint_by_id(
        self, cursor: Any, snapshot_id: str, *, required: bool = False
    ) -> OddsCheckpoint | None:
        cursor.execute(
            "SELECT snapshot_id, series_id, odd, observed_at, captured_at, source "
            "FROM quote_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        row = cursor.fetchone()
        if row is None and required:
            raise PickMonitoringConflictError("referenced quote snapshot is missing")
        return None if row is None else self._checkpoint(row)

    @staticmethod
    def _candidate_sql(order: str) -> str:
        ordering = (
            "q.captured_at ASC, q.observed_at ASC, q.snapshot_id ASC"
            if order == "opening"
            else "q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC"
        )
        return (
            "SELECT q.snapshot_id, q.series_id, q.odd, q.observed_at, q.captured_at, q.source "
            "FROM quote_snapshots q JOIN LATERAL ("
            "SELECT f.kickoff_at, f.provider_status FROM fixture_observations f "
            "WHERE f.fixture_id = %s AND f.observed_at <= q.captured_at "
            "AND f.persisted_at <= q.captured_at "
            "ORDER BY f.observed_at DESC, f.fixture_observation_id DESC LIMIT 1"
            ") observed_fixture ON TRUE "
            "WHERE q.series_id = %s AND q.source = %s AND q.observed_at < %s "
            "AND q.captured_at < %s AND q.captured_at <= %s "
            "AND observed_fixture.provider_status = ANY(%s) "
            "AND q.observed_at < observed_fixture.kickoff_at "
            "AND q.captured_at < observed_fixture.kickoff_at ORDER BY " + ordering
        )

    def _candidate(
        self,
        cursor: Any,
        *,
        fixture_id: str,
        series_id: str,
        source: str,
        cutoff_at: datetime,
        allowed_statuses: tuple[str, ...],
        order: str,
        available_at: datetime | None = None,
    ) -> OddsCheckpoint | None:
        available = cutoff_at if available_at is None else available_at
        cursor.execute(
            self._candidate_sql(order) + " LIMIT 1",
            (
                fixture_id,
                series_id,
                source,
                cutoff_at,
                cutoff_at,
                available,
                list(allowed_statuses),
            ),
        )
        row = cursor.fetchone()
        return None if row is None else self._checkpoint(row)

    def _history(
        self,
        cursor: Any,
        *,
        fixture_id: str,
        series_id: str,
        source: str,
        cutoff_at: datetime,
        allowed_statuses: tuple[str, ...],
        available_at: datetime,
    ) -> tuple[OddsCheckpoint, ...]:
        cursor.execute(
            self._candidate_sql("opening"),
            (
                fixture_id,
                series_id,
                source,
                cutoff_at,
                cutoff_at,
                available_at,
                list(allowed_statuses),
            ),
        )
        return tuple(self._checkpoint(row) for row in cursor.fetchall())
