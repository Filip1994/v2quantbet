"""PostgreSQL authoritative result, settlement, ledger and realized-CLV boundary."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any

from h2h.domain.fixture_result import FixtureResultObservation, ResultClassification
from h2h.domain.odds import Market, Selection
from h2h.domain.settlement import (
    CLV_METHOD_VERSION,
    MONEY_ROUNDING_VERSION,
    SETTLEMENT_RULE_VERSION,
    ClvAvailability,
    ResultSettlementPolicy,
    SettlementOutcome,
    realized_clv_ppm,
    settle_market,
    settlement_amounts,
)
from h2h.persistence.result_settlement import (
    ClvResult,
    ResultNotStableError,
    ResultPersistenceConflictError,
    SettlementConflictError,
    SettlementRecord,
)


ConnectionFactory = Callable[[], Any]


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _fact_id(prefix: str, value: str) -> str:
    return f"{prefix}:" + sha256(value.encode("utf-8")).hexdigest()


class PostgreSQLResultSettlementRepository:
    def __init__(
        self,
        policy: ResultSettlementPolicy,
        database_url: str | None = None,
        *,
        connect: ConnectionFactory | None = None,
    ) -> None:
        if not isinstance(policy, ResultSettlementPolicy):
            raise TypeError("policy must be a ResultSettlementPolicy")
        self.policy = policy
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

    def reconcile(self, *, reconciled_at: datetime) -> tuple[str, ...]:
        now = _utc(reconciled_at, "reconciled_at")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "WITH tracked AS ("
                "SELECT fixture_id FROM registered_picks "
                "UNION SELECT fixture_id FROM research_signals"
                ") INSERT INTO fixture_result_acquisition_states "
                "(fixture_id, phase, next_check_at, updated_at, version) "
                "SELECT DISTINCT r.fixture_id, 'WAITING', "
                "latest.kickoff_at + (%s * interval '1 second'), %s, 1 "
                "FROM tracked r JOIN LATERAL ("
                "SELECT kickoff_at FROM fixture_observations f WHERE f.fixture_id = r.fixture_id "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
                ") latest ON TRUE LEFT JOIN fixture_result_acquisition_states s "
                "ON s.fixture_id = r.fixture_id WHERE s.fixture_id IS NULL "
                "ON CONFLICT DO NOTHING RETURNING fixture_id",
                (self.policy.initial_delay_seconds, now),
            )
            return tuple(row[0] for row in cursor.fetchall())

    def claim_due(
        self, *, claimed_at: datetime, limit: int | None = None
    ) -> tuple[str, ...]:
        now = _utc(claimed_at, "claimed_at")
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError("limit must be a positive integer")
        claim_limit = self.policy.claim_limit if limit is None else min(limit, self.policy.claim_limit)
        lease = now + timedelta(seconds=self.policy.claim_lease_seconds)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id FROM fixture_result_acquisition_states "
                "WHERE phase <> 'COMPLETE' AND next_check_at <= %s "
                "AND (lease_expires_at IS NULL OR lease_expires_at <= %s) "
                "ORDER BY next_check_at, fixture_id FOR UPDATE SKIP LOCKED LIMIT %s",
                (now, now, claim_limit),
            )
            rows = cursor.fetchall()
            if rows:
                cursor.execute(
                    "UPDATE fixture_result_acquisition_states SET lease_expires_at = %s, "
                    "updated_at = %s, version = version + 1 WHERE fixture_id = ANY(%s)",
                    (lease, now, [row[0] for row in rows]),
                )
            return tuple(row[0] for row in rows)

    def has_due_results(self, *, as_of: datetime) -> bool:
        now = _utc(as_of, "as_of")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM fixture_result_acquisition_states "
                "WHERE phase <> 'COMPLETE' AND next_check_at <= %s "
                "AND (lease_expires_at IS NULL OR lease_expires_at <= %s))",
                (now, now),
            )
            return bool(cursor.fetchone()[0])

    def provider_contexts(self, fixture_ids: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
        if not fixture_ids:
            return ()
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id, provider_fixture_id::bigint FROM fixtures "
                "WHERE fixture_id = ANY(%s) AND provider = 'api-football' ORDER BY fixture_id",
                (list(fixture_ids),),
            )
            return tuple((row[0], int(row[1])) for row in cursor.fetchall())

    def persist_result(
        self, result: FixtureResultObservation, *, checked_at: datetime
    ) -> FixtureResultObservation:
        checked = _utc(checked_at, "checked_at")
        if not isinstance(result, FixtureResultObservation):
            raise TypeError("result must be a FixtureResultObservation")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT provider, provider_fixture_id, provider_home_team_id, "
                "provider_away_team_id FROM fixtures WHERE fixture_id = %s FOR UPDATE",
                (result.fixture_id,),
            )
            anchor = cursor.fetchone()
            expected = (
                result.provider,
                result.provider_fixture_id,
                result.provider_home_team_id,
                result.provider_away_team_id,
            )
            if anchor is None or tuple(anchor) != expected:
                raise ResultPersistenceConflictError("result contradicts durable fixture identity")
            self._append_fixture_observation(cursor, result, checked)
            cursor.execute(
                "INSERT INTO fixture_result_observations ("
                "result_observation_id, fixture_id, provider, provider_fixture_id, "
                "provider_status, provider_kickoff_at, provider_home_team_id, "
                "provider_away_team_id, goals_home, goals_away, fulltime_home, fulltime_away, "
                "extratime_home, extratime_away, penalty_home, penalty_away, "
                "regulation_home_goals, regulation_away_goals, result_classification, "
                "settlement_fingerprint, normalizer_version, provider_record_sha256, "
                "provider_record, first_acquired_at) VALUES ("
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s::jsonb, %s) ON CONFLICT DO NOTHING",
                (
                    result.result_observation_id,
                    result.fixture_id,
                    result.provider,
                    result.provider_fixture_id,
                    result.provider_status,
                    result.provider_kickoff_at,
                    result.provider_home_team_id,
                    result.provider_away_team_id,
                    *result.goals,
                    *result.fulltime,
                    *result.extratime,
                    *result.penalty,
                    *result.regulation_goals,
                    result.classification.value,
                    result.settlement_fingerprint,
                    result.normalizer_version,
                    result.provider_record_sha256,
                    json.dumps(result.provider_record, sort_keys=True, separators=(",", ":")),
                    result.first_acquired_at,
                ),
            )
            cursor.execute(
                "SELECT provider_record_sha256, result_classification, settlement_fingerprint "
                "FROM fixture_result_observations WHERE result_observation_id = %s",
                (result.result_observation_id,),
            )
            stored = cursor.fetchone()
            if stored != (
                result.provider_record_sha256,
                result.classification.value,
                result.settlement_fingerprint,
            ):
                raise ResultPersistenceConflictError("result observation identity conflicts")
            self._advance_state(cursor, result, checked)
        return result

    def _advance_state(self, cursor: Any, result: FixtureResultObservation, checked: datetime) -> None:
        cursor.execute(
            "SELECT candidate_settlement_fingerprint, candidate_first_seen_at, "
            "candidate_confirmation_count, correction_required, "
            "contradicting_observation_id FROM fixture_result_acquisition_states "
            "WHERE fixture_id = %s FOR UPDATE",
            (result.fixture_id,),
        )
        state = cursor.fetchone()
        if state is None:
            raise ResultPersistenceConflictError("fixture acquisition state is missing")
        if result.is_terminal_candidate:
            same = state[0] == result.settlement_fingerprint
            first_seen = state[1] if same else checked
            count = int(state[2]) + 1 if same else 1
            phase = "STABILIZING"
            next_check = checked + timedelta(seconds=self.policy.finality_delay_seconds)
            candidate_id = result.result_observation_id
            fingerprint = result.settlement_fingerprint
        else:
            first_seen = candidate_id = fingerprint = None
            count = 0
            phase = "POLLING"
            interval = self.policy.poll_interval_seconds
            if result.provider_status in {"SUSP", "INT"}:
                interval = self.policy.suspended_poll_interval_seconds
            elif result.provider_status == "PST":
                interval = self.policy.postponed_poll_interval_seconds
            next_check = checked + timedelta(seconds=interval)
        cursor.execute(
            "SELECT anchor.result_observation_id, anchor.settlement_fingerprint, "
            "anchor.occurred_at FROM ("
            "SELECT e.result_observation_id, settled.settlement_fingerprint, e.occurred_at "
            "FROM pick_settlement_events e "
            "JOIN fixture_result_observations settled "
            "ON settled.result_observation_id = e.result_observation_id "
            "WHERE e.fixture_id = %s AND e.event_kind = 'NORMAL' "
            "UNION ALL "
            "SELECT r.result_observation_id, settled.settlement_fingerprint, r.finalized_at "
            "FROM research_fixture_result_finalizations r "
            "JOIN fixture_result_observations settled "
            "ON settled.result_observation_id = r.result_observation_id "
            "WHERE r.fixture_id = %s"
            ") anchor ORDER BY anchor.occurred_at LIMIT 1",
            (result.fixture_id, result.fixture_id),
        )
        settled = cursor.fetchone()
        newly_confirmed_correction = bool(
            settled
            and result.settlement_fingerprint
            and settled[1] != result.settlement_fingerprint
            and result.is_terminal_candidate
            and count >= 2
            and checked - first_seen >= timedelta(seconds=self.policy.finality_delay_seconds)
        )
        correction = bool(state[3]) or newly_confirmed_correction
        contradicting_observation_id = (
            result.result_observation_id if newly_confirmed_correction else state[4]
        )
        if settled:
            correction_deadline = settled[2] + timedelta(
                seconds=self.policy.correction_window_seconds
            )
            if correction or checked >= correction_deadline:
                phase = "COMPLETE"
                next_check = max(checked, correction_deadline)
            elif result.is_terminal_candidate and settled[1] == result.settlement_fingerprint:
                phase = "POST_SETTLEMENT_RECHECK"
                next_check = min(checked + timedelta(hours=6), correction_deadline)
        cursor.execute(
            "UPDATE fixture_result_acquisition_states SET phase = %s, "
            "current_observation_id = %s, candidate_observation_id = %s, "
            "candidate_settlement_fingerprint = %s, candidate_first_seen_at = %s, "
            "candidate_confirmation_count = %s, next_check_at = %s, lease_expires_at = NULL, "
            "last_checked_at = %s, correction_required = %s, "
            "contradicting_observation_id = %s, updated_at = %s, version = version + 1 "
            "WHERE fixture_id = %s",
            (
                phase,
                result.result_observation_id,
                candidate_id,
                fingerprint,
                first_seen,
                count,
                next_check,
                checked,
                correction,
                contradicting_observation_id,
                checked,
                result.fixture_id,
            ),
        )

    def stable_result(self, fixture_id: str, *, as_of: datetime) -> str | None:
        now = _utc(as_of, "as_of")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT candidate_observation_id, candidate_first_seen_at, "
                "candidate_confirmation_count, last_checked_at FROM fixture_result_acquisition_states "
                "WHERE fixture_id = %s",
                (fixture_id,),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None or int(row[2]) < 2 or row[3] is None:
                return None
            if row[3] - row[1] < timedelta(seconds=self.policy.finality_delay_seconds):
                return None
            if now < row[3]:
                return None
            return row[0]

    def unsettled_pick_ids(self, fixture_id: str) -> tuple[str, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.pick_id FROM registered_picks r WHERE r.fixture_id = %s "
                "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events e "
                "WHERE e.pick_id = r.pick_id AND e.event_kind = 'NORMAL') "
                "ORDER BY r.registered_at, r.pick_id",
                (fixture_id,),
            )
            return tuple(row[0] for row in cursor.fetchall())

    def pick_ids_for_fixture(self, fixture_id: str) -> tuple[str, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id FROM registered_picks WHERE fixture_id = %s "
                "ORDER BY registered_at, pick_id",
                (fixture_id,),
            )
            return tuple(row[0] for row in cursor.fetchall())

    def settle_pick(
        self, pick_id: str, result_observation_id: str, *, settled_at: datetime
    ) -> SettlementRecord:
        settled = _utc(settled_at, "settled_at")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id, bankroll_account_id FROM registered_picks WHERE pick_id = %s",
                (pick_id,),
            )
            initial = cursor.fetchone()
            if initial is None:
                raise LookupError(f"registered pick {pick_id!r} does not exist")
            fixture_id, account_id = initial
            cursor.execute("SELECT fixture_id FROM fixtures WHERE fixture_id = %s FOR UPDATE", (fixture_id,))
            if cursor.fetchone() is None:
                raise ResultPersistenceConflictError("fixture disappeared")
            cursor.execute(
                "SELECT currency FROM bankroll_accounts WHERE bankroll_account_id = %s FOR UPDATE",
                (account_id,),
            )
            account = cursor.fetchone()
            if account is None:
                raise ResultPersistenceConflictError("bankroll account disappeared")
            cursor.execute(
                "SELECT r.fixture_id, r.market, r.selection, r.entry_snapshot_id, r.stake_minor, "
                "r.currency, r.bankroll_account_id, e.selected_series_id, e.source, "
                "q.odd::text::numeric FROM registered_picks r "
                "JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id "
                "JOIN quote_snapshots q ON q.snapshot_id = r.entry_snapshot_id "
                "WHERE r.pick_id = %s FOR UPDATE OF r",
                (pick_id,),
            )
            pick = cursor.fetchone()
            if pick is None or pick[0] != fixture_id or pick[6] != account_id:
                raise ResultPersistenceConflictError("pick context changed while locking")
            cursor.execute(
                "SELECT settlement_event_id, result_observation_id, outcome, entry_odd_decimal, "
                "stake_minor, gross_return_minor, realized_pnl_minor, ledger_entry_id, occurred_at "
                "FROM pick_settlement_events WHERE pick_id = %s AND event_kind = 'NORMAL'",
                (pick_id,),
            )
            replay = cursor.fetchone()
            if replay is not None:
                if replay[1] != result_observation_id:
                    raise SettlementConflictError("pick already has a different normal settlement")
                return SettlementRecord(
                    replay[0], pick_id, replay[1], SettlementOutcome(replay[2]),
                    Decimal(replay[3]), int(replay[4]), int(replay[5]), int(replay[6]),
                    replay[7], replay[8]
                )
            cursor.execute(
                "SELECT provider_status, provider_kickoff_at, regulation_home_goals, "
                "regulation_away_goals, result_classification, settlement_fingerprint, "
                "provider, provider_fixture_id, provider_home_team_id, provider_away_team_id, "
                "goals_home, goals_away, fulltime_home, fulltime_away, extratime_home, "
                "extratime_away, penalty_home, penalty_away, normalizer_version, "
                "provider_record_sha256, provider_record, first_acquired_at, persisted_at "
                "FROM fixture_result_observations WHERE result_observation_id = %s "
                "AND fixture_id = %s",
                (result_observation_id, fixture_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise ResultPersistenceConflictError("result does not belong to pick fixture")
            cursor.execute(
                "SELECT candidate_observation_id, candidate_first_seen_at, "
                "candidate_confirmation_count, last_checked_at FROM fixture_result_acquisition_states "
                "WHERE fixture_id = %s FOR UPDATE",
                (fixture_id,),
            )
            state = cursor.fetchone()
            if (
                state is None
                or state[0] != result_observation_id
                or int(state[2]) < 2
                or state[3] - state[1] < timedelta(seconds=self.policy.finality_delay_seconds)
            ):
                raise ResultNotStableError("result has not satisfied stable finality")
            result = self._result_from_row(result_observation_id, fixture_id, row)
            outcome = settle_market(Market(pick[1]), Selection(pick[2]), result)
            amounts = settlement_amounts(
                stake_minor=int(pick[4]), entry_odd_decimal=Decimal(pick[9]), outcome=outcome
            )
            cursor.execute(
                "SELECT ledger_entry_id, account_sequence, balance_after_minor "
                "FROM bankroll_ledger_entries WHERE bankroll_account_id = %s "
                "ORDER BY account_sequence DESC LIMIT 1",
                (account_id,),
            )
            last = cursor.fetchone()
            cursor.execute(
                "SELECT ledger_entry_id, amount_minor FROM bankroll_ledger_entries "
                "WHERE pick_id = %s AND entry_type = 'STAKE_RESERVED'",
                (pick_id,),
            )
            reservation = cursor.fetchone()
            if last is None or reservation is None or int(reservation[1]) != -int(pick[4]):
                raise ResultPersistenceConflictError("exact stake reservation is missing")
            event_id = _fact_id("pick-settlement-event-v1", f"normal:{pick_id}")
            ledger_id = _fact_id("bankroll-entry-v1", f"settlement:{pick_id}")
            cursor.execute(
                "INSERT INTO bankroll_ledger_entries (ledger_entry_id, bankroll_account_id, "
                "account_sequence, entry_type, amount_minor, balance_after_minor, occurred_at, "
                "pick_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    ledger_id, account_id, int(last[1]) + 1, amounts.ledger_entry_type,
                    amounts.ledger_delta_minor, int(last[2]) + amounts.ledger_delta_minor,
                    settled, pick_id,
                ),
            )
            cursor.execute(
                "INSERT INTO pick_settlement_events (settlement_event_id, pick_id, fixture_id, "
                "event_kind, prior_event_id, result_observation_id, outcome, "
                "settlement_rule_version, rounding_version, entry_snapshot_id, entry_odd_decimal, "
                "stake_minor, gross_return_minor, realized_pnl_minor, ledger_delta_minor, "
                "bankroll_account_id, currency, ledger_entry_id, candidate_first_seen_at, "
                "confirmed_at, confirmation_count, request_id, reason, actor, occurred_at) "
                "VALUES (%s, %s, %s, 'NORMAL', NULL, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s)",
                (
                    event_id, pick_id, fixture_id, result_observation_id, outcome.value,
                    SETTLEMENT_RULE_VERSION, MONEY_ROUNDING_VERSION, pick[3],
                    amounts.entry_odd_decimal, amounts.stake_minor, amounts.gross_return_minor,
                    amounts.realized_pnl_minor, amounts.ledger_delta_minor, account_id, pick[5],
                    ledger_id, state[1], state[3], int(state[2]), f"normal:{pick_id}", settled,
                ),
            )
            cursor.execute(
                "UPDATE fixture_result_acquisition_states SET phase = 'POST_SETTLEMENT_RECHECK', "
                "next_check_at = %s, updated_at = %s, version = version + 1 "
                "WHERE fixture_id = %s",
                (settled + timedelta(hours=6), settled, fixture_id),
            )
            return SettlementRecord(
                event_id, pick_id, result_observation_id, outcome, amounts.entry_odd_decimal,
                amounts.stake_minor, amounts.gross_return_minor, amounts.realized_pnl_minor,
                ledger_id, settled,
            )

    def finalize_clv(self, pick_id: str, *, realized_at: datetime) -> ClvResult:
        realized = _utc(realized_at, "realized_at")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pick_id FROM registered_picks WHERE pick_id = %s FOR UPDATE", (pick_id,))
            if cursor.fetchone() is None:
                raise LookupError(f"registered pick {pick_id!r} does not exist")
            cursor.execute(
                "SELECT c.clv_fact_id, c.clv_ppm FROM pick_realized_clv c WHERE c.pick_id = %s",
                (pick_id,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                return ClvResult(ClvAvailability.AVAILABLE, int(existing[1]), existing[0])
            cursor.execute(
                "SELECT e.settlement_event_id, e.result_observation_id, e.entry_snapshot_id, "
                "e.entry_odd_decimal, r.provider_kickoff_at FROM pick_settlement_events e "
                "JOIN fixture_result_observations r "
                "ON r.result_observation_id = e.result_observation_id "
                "WHERE e.pick_id = %s AND e.event_kind = 'NORMAL'",
                (pick_id,),
            )
            settlement = cursor.fetchone()
            if settlement is None:
                return ClvResult(ClvAvailability.PENDING_SETTLEMENT)
            cursor.execute(
                "SELECT f.finalization_id, f.cutoff_at, f.series_id, f.source, f.outcome, "
                "f.closing_snapshot_id, e.selected_series_id, e.source "
                "FROM pick_closing_finalizations f JOIN registered_picks r ON r.pick_id = f.pick_id "
                "JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id "
                "WHERE f.pick_id = %s",
                (pick_id,),
            )
            closing = cursor.fetchone()
            if closing is None or closing[4] == "NO_VALID_QUOTE":
                return ClvResult(ClvAvailability.NO_VALID_CLOSING)
            if closing[4] == "STALE_QUOTE":
                return ClvResult(ClvAvailability.STALE_CLOSING)
            if closing[1] != settlement[4]:
                return ClvResult(ClvAvailability.KICKOFF_CHANGED_AFTER_CLOSING)
            if closing[2] != closing[6] or closing[3] != closing[7]:
                return ClvResult(ClvAvailability.PROVENANCE_CONFLICT)
            cursor.execute(
                "SELECT q.snapshot_id, q.series_id, q.source, q.odd::text::numeric "
                "FROM quote_snapshots q WHERE q.snapshot_id IN (%s, %s) "
                "ORDER BY q.snapshot_id",
                (settlement[2], closing[5]),
            )
            quotes = {row[0]: row for row in cursor.fetchall()}
            entry = quotes.get(settlement[2])
            close = quotes.get(closing[5])
            if (
                entry is None or close is None or entry[1:3] != (closing[2], closing[3])
                or close[1:3] != (closing[2], closing[3])
            ):
                return ClvResult(ClvAvailability.PROVENANCE_CONFLICT)
            value = realized_clv_ppm(Decimal(entry[3]), Decimal(close[3]))
            fact_id = _fact_id("pick-realized-clv-v1", pick_id)
            cursor.execute(
                "INSERT INTO pick_realized_clv (clv_fact_id, pick_id, settlement_event_id, "
                "closing_finalization_id, entry_snapshot_id, closing_snapshot_id, series_id, "
                "source, entry_odd_decimal, closing_odd_decimal, method_version, clv_ppm, "
                "realized_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    fact_id, pick_id, settlement[0], closing[0], settlement[2], closing[5],
                    closing[2], closing[3], Decimal(entry[3]), Decimal(close[3]),
                    CLV_METHOD_VERSION, value, realized,
                ),
            )
            return ClvResult(ClvAvailability.AVAILABLE, value, fact_id)

    @staticmethod
    def _append_fixture_observation(cursor: Any, result: FixtureResultObservation, checked: datetime) -> None:
        cursor.execute(
            "SELECT home_team, away_team, competition_name, country, competition_type "
            "FROM fixture_observations WHERE fixture_id = %s "
            "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
            (result.fixture_id,),
        )
        context = cursor.fetchone()
        if context is None:
            raise ResultPersistenceConflictError("durable fixture observation is missing")
        source = "api-football-result"
        observation_id = _fact_id(
            "fixture-observation-v1", f"{result.fixture_id}|{checked.isoformat()}|{source}"
        )
        cursor.execute(
            "INSERT INTO fixture_observations (fixture_observation_id, fixture_id, home_team, "
            "away_team, competition_name, country, competition_type, kickoff_at, "
            "provider_status, source, observed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s) ON CONFLICT DO NOTHING",
            (observation_id, result.fixture_id, *context, result.provider_kickoff_at,
             result.provider_status, source, checked),
        )

    @staticmethod
    def _result_from_row(result_id: str, fixture_id: str, row: tuple[Any, ...]) -> FixtureResultObservation:
        record = row[20]
        if isinstance(record, str):
            record = json.loads(record)
        return FixtureResultObservation(
            result_id, fixture_id, row[6], row[7], row[0], row[1], int(row[8]), int(row[9]),
            (row[10], row[11]), (row[12], row[13]), (row[14], row[15]), (row[16], row[17]),
            (row[2], row[3]), ResultClassification(row[4]), row[5], row[18], row[19], record,
            row[21], row[22],
        )