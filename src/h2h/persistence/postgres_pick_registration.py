"""Atomic PostgreSQL implementation of Task #10 pick registration."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from h2h.decisions.pick_eligibility import evaluate_persisted_eligibility
from h2h.domain.final_quote import FinalQuoteClaim, FinalQuoteStatus
from h2h.domain.fixture_record import FixtureObservation
from h2h.domain.odds import Market, Selection
from h2h.domain.pick_decision import (
    BankrollRiskSnapshot,
    DecisionOutcome,
    FixedStakeDecision,
    PickDecision,
    PickLifecycleState,
    RegisteredPick,
    RegistrationResult,
    RejectionStage,
)
from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.persistence.pick_registration import (
    BankrollBootstrapConflictError,
    BankrollBootstrapResult,
    BankrollNotBootstrappedError,
    RegistrationPersistenceConflictError,
    RegistrationProvenanceError,
)
from h2h.persistence.postgres_value_evaluations import PostgreSQLValueEvaluationRepository
from h2h.risk.pick_risk import evaluate_risk, fixed_stake


ConnectionFactory = Callable[[], Any]

_EVALUATION_COLUMNS = (
    "evaluation_id, fixture_id, prediction_id, model_version_id, selected_series_id, "
    "companion_series_id, selected_snapshot_id, companion_snapshot_id, bookmaker_id, "
    "bookmaker_key, market, selected_selection, companion_selection, quote_observed_at, "
    "source, selected_captured_at, companion_captured_at, selected_odd, companion_odd, "
    "selected_raw_implied_probability, companion_raw_implied_probability, overround, "
    "devig_method_version, selected_devig_probability, model_probability, edge, "
    "expected_value, evaluated_at, persisted_at"
)


def _fact_id(prefix: str, value: str) -> str:
    return f"{prefix}:" + sha256(value.encode("utf-8")).hexdigest()


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


class PostgreSQLPickRegistrationRepository:
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

    def bootstrap_bankroll(
        self, policy: RegistrationPolicyConfig, *, occurred_at: datetime
    ) -> BankrollBootstrapResult:
        occurred = _utc(occurred_at, "occurred_at")
        entry_id = _fact_id("bankroll-entry-v1", f"initial:{policy.bankroll_account_id}")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO bankroll_accounts "
                "(bankroll_account_id, currency, created_at) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (policy.bankroll_account_id, policy.currency, occurred),
            )
            cursor.execute(
                "SELECT currency FROM bankroll_accounts WHERE bankroll_account_id = %s FOR UPDATE",
                (policy.bankroll_account_id,),
            )
            account = cursor.fetchone()
            if account is None or account[0] != policy.currency:
                raise BankrollBootstrapConflictError("bankroll account currency conflicts")
            cursor.execute(
                "SELECT ledger_entry_id, amount_minor, balance_after_minor "
                "FROM bankroll_ledger_entries WHERE bankroll_account_id = %s "
                "AND entry_type = 'INITIAL_BANKROLL'",
                (policy.bankroll_account_id,),
            )
            initial = cursor.fetchone()
            if initial is None:
                cursor.execute(
                    "INSERT INTO bankroll_ledger_entries "
                    "(ledger_entry_id, bankroll_account_id, account_sequence, entry_type, "
                    "amount_minor, balance_after_minor, occurred_at, pick_id) "
                    "VALUES (%s, %s, 1, 'INITIAL_BANKROLL', %s, %s, %s, NULL)",
                    (
                        entry_id,
                        policy.bankroll_account_id,
                        policy.initial_bankroll_minor,
                        policy.initial_bankroll_minor,
                        occurred,
                    ),
                )
            elif initial != (
                entry_id,
                policy.initial_bankroll_minor,
                policy.initial_bankroll_minor,
            ):
                raise BankrollBootstrapConflictError("initial bankroll fact conflicts")
        return BankrollBootstrapResult(
            policy.bankroll_account_id,
            entry_id,
            policy.initial_bankroll_minor,
            policy.currency,
        )

    def register(
        self,
        evaluation_id: str,
        registration_request_id: str,
        policy: RegistrationPolicyConfig,
        *,
        decided_at: datetime,
        final_quote_verification_id: str | None = None,
    ) -> RegistrationResult:
        decided = _utc(decided_at, "decided_at")
        if not isinstance(registration_request_id, str) or not registration_request_id.strip():
            raise ValueError("registration_request_id must not be blank")
        decision_id = _fact_id("pick-decision-v1", registration_request_id)
        with self.connect() as connection, connection.cursor() as cursor:
            evaluation = self._load_evaluation(cursor, evaluation_id)
            self._verify_prediction_provenance(cursor, evaluation)
            self._persist_policy(cursor, policy, decided)
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (registration_request_id,),
            )
            replay = self._load_result(cursor, registration_request_id)
            if replay is not None:
                if (
                    replay.decision.evaluation_id != evaluation_id
                    or replay.decision.policy_config_fingerprint != policy.fingerprint
                ):
                    raise RegistrationPersistenceConflictError(
                        "registration request was reused with different input"
                    )
                return replay
            fixture = self._latest_fixture_observation(cursor, evaluation.fixture_id, decided)
            eligibility = evaluate_persisted_eligibility(
                evaluation,
                fixture,
                policy,
                decided_at=decided,
                quote_age_is_warning=final_quote_verification_id is not None,
            )
            if (
                not eligibility
                and final_quote_verification_id is not None
                and not self._valid_final_verification(
                    cursor,
                    final_quote_verification_id,
                    evaluation.evaluation_id,
                )
            ):
                from h2h.domain.pick_decision import EligibilityRejectionCode

                eligibility = (EligibilityRejectionCode.FINAL_QUOTE_REFRESH_REQUIRED,)
            if eligibility:
                decision = PickDecision(
                    decision_id,
                    registration_request_id,
                    evaluation.evaluation_id,
                    fixture.fixture_observation_id,
                    policy.fingerprint,
                    decided,
                    DecisionOutcome.REJECTED,
                    RejectionStage.ELIGIBILITY,
                    tuple(code.value for code in eligibility),
                )
                self._insert_decision(cursor, decision, final_quote_verification_id)
                return RegistrationResult(decision, None)

            # Lock ordering is part of the production contract: fixture, then bankroll.
            cursor.execute(
                "SELECT fixture_id FROM fixtures WHERE fixture_id = %s FOR UPDATE",
                (evaluation.fixture_id,),
            )
            if cursor.fetchone() is None:
                raise RegistrationProvenanceError("fixture coordination row is missing")
            cursor.execute(
                "SELECT currency FROM bankroll_accounts WHERE bankroll_account_id = %s FOR UPDATE",
                (policy.bankroll_account_id,),
            )
            account = cursor.fetchone()
            if account is None:
                raise BankrollNotBootstrappedError(
                    "configured bankroll account is not bootstrapped"
                )
            if account[0] != policy.currency:
                raise RegistrationProvenanceError("bankroll currency contradicts policy")
            cursor.execute(
                "SELECT ledger_entry_id, account_sequence, balance_after_minor "
                "FROM bankroll_ledger_entries WHERE bankroll_account_id = %s "
                "ORDER BY account_sequence DESC LIMIT 1",
                (policy.bankroll_account_id,),
            )
            ledger = cursor.fetchone()
            if ledger is None:
                raise BankrollNotBootstrappedError("bankroll has no initial funding fact")
            cursor.execute(
                "SELECT amount_minor FROM bankroll_ledger_entries "
                "WHERE bankroll_account_id = %s AND entry_type = 'INITIAL_BANKROLL'",
                (policy.bankroll_account_id,),
            )
            initial = cursor.fetchone()
            if initial is None or int(initial[0]) != policy.initial_bankroll_minor:
                raise RegistrationProvenanceError(
                    "initial bankroll funding contradicts registration policy"
                )
            cursor.execute(
                "SELECT COALESCE(SUM(-l.amount_minor), 0) FROM bankroll_ledger_entries l "
                "WHERE l.bankroll_account_id = %s AND l.entry_type = 'STAKE_RESERVED' "
                "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events e "
                "WHERE e.pick_id = l.pick_id AND e.outcome IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events successor "
                "WHERE successor.prior_event_id = e.settlement_event_id))",
                (policy.bankroll_account_id,),
            )
            open_exposure = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM registered_picks WHERE fixture_id = %s)",
                (evaluation.fixture_id,),
            )
            duplicate = bool(cursor.fetchone()[0])
            stake = fixed_stake(policy)
            snapshot = BankrollRiskSnapshot(
                policy.bankroll_account_id,
                ledger[0],
                int(ledger[2]),
                open_exposure,
                policy.max_stake_per_pick_minor,
                policy.max_open_exposure_minor,
            )
            risk = evaluate_risk(stake, snapshot, duplicate_fixture=duplicate)
            if risk:
                decision = PickDecision(
                    decision_id,
                    registration_request_id,
                    evaluation.evaluation_id,
                    fixture.fixture_observation_id,
                    policy.fingerprint,
                    decided,
                    DecisionOutcome.REJECTED,
                    RejectionStage.RISK,
                    tuple(code.value for code in risk),
                    stake,
                    snapshot,
                )
                self._insert_decision(cursor, decision, final_quote_verification_id)
                return RegistrationResult(decision, None)

            decision = PickDecision(
                decision_id,
                registration_request_id,
                evaluation.evaluation_id,
                fixture.fixture_observation_id,
                policy.fingerprint,
                decided,
                DecisionOutcome.APPROVED,
                None,
                (),
                stake,
                snapshot,
            )
            self._insert_decision(cursor, decision, final_quote_verification_id)
            pick = RegisteredPick(
                _fact_id("registered-pick-v1", decision_id),
                decision_id,
                evaluation.evaluation_id,
                evaluation.fixture_id,
                evaluation.market,
                evaluation.selected_selection,
                evaluation.selected_snapshot_id,
                decided,
                stake.amount_minor,
                stake.currency,
                policy.bankroll_account_id,
                policy.fingerprint,
            )
            cursor.execute(
                "INSERT INTO registered_picks "
                "(pick_id, decision_id, evaluation_id, fixture_id, market, selection, "
                "entry_snapshot_id, registered_at, stake_minor, currency, bankroll_account_id, "
                "config_fingerprint, initial_state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    pick.pick_id,
                    pick.decision_id,
                    pick.evaluation_id,
                    pick.fixture_id,
                    pick.market.value,
                    pick.selection.value,
                    pick.entry_snapshot_id,
                    pick.registered_at,
                    pick.stake_minor,
                    pick.currency,
                    pick.bankroll_account_id,
                    pick.policy_config_fingerprint,
                    pick.initial_state.value,
                ),
            )
            self._after_pick_insert(cursor, pick)
            cursor.execute(
                "INSERT INTO bankroll_ledger_entries "
                "(ledger_entry_id, bankroll_account_id, account_sequence, entry_type, "
                "amount_minor, balance_after_minor, occurred_at, pick_id) "
                "VALUES (%s, %s, %s, 'STAKE_RESERVED', %s, %s, %s, %s)",
                (
                    _fact_id("bankroll-entry-v1", f"reserve:{pick.pick_id}"),
                    policy.bankroll_account_id,
                    int(ledger[1]) + 1,
                    -stake.amount_minor,
                    snapshot.balance_before_minor - stake.amount_minor,
                    decided,
                    pick.pick_id,
                ),
            )
            return RegistrationResult(decision, pick)

    def _after_pick_insert(self, cursor: Any, pick: RegisteredPick) -> None:
        """Test seam for proving transaction rollback; production intentionally does nothing."""

    @staticmethod
    def _load_evaluation(cursor: Any, evaluation_id: str) -> Any:
        cursor.execute(
            f"SELECT {_EVALUATION_COLUMNS} FROM value_evaluations WHERE evaluation_id = %s",
            (evaluation_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError(f"value evaluation {evaluation_id!r} does not exist")
        try:
            value = PostgreSQLValueEvaluationRepository._row(row)
            value.validate_arithmetic()
            return value
        except (TypeError, ValueError) as exc:
            raise RegistrationProvenanceError("stored value evaluation is invalid") from exc

    @staticmethod
    def _verify_prediction_provenance(cursor: Any, evaluation: Any) -> None:
        cursor.execute(
            "SELECT p.fixture_observation_id FROM fixture_predictions p "
            "JOIN dixon_coles_model_versions m ON m.model_version_id = p.model_version_id "
            "AND m.provider = p.provider AND m.team_id_namespace = p.team_id_namespace "
            "AND m.league_id = p.league_id AND m.season = p.season "
            "JOIN dixon_coles_active_models a ON a.provider = p.provider "
            "AND a.team_id_namespace = p.team_id_namespace AND a.league_id = p.league_id "
            "AND a.season = p.season AND a.model_version_id = p.model_version_id "
            "AND a.generation = p.active_generation AND a.activated_at = p.model_activated_at "
            "LEFT JOIN model_coverage_scopes c ON c.provider = p.provider "
            "AND c.team_id_namespace = p.team_id_namespace AND c.league_id = p.league_id "
            "AND c.season = p.season "
            "WHERE p.prediction_id = %s AND p.fixture_id = %s AND p.model_version_id = %s "
            "AND (c.status IS NULL OR c.status = 'ACTIVE')",
            (evaluation.prediction_id, evaluation.fixture_id, evaluation.model_version_id),
        )

    def preliminary_rejection_codes(
        self,
        evaluation_id: str,
        policy: RegistrationPolicyConfig,
        *,
        checked_at: datetime,
    ) -> tuple[str, ...]:
        """Read-only candidate gate; final registration repeats every check under locks."""
        checked = _utc(checked_at, "checked_at")
        with self.connect() as connection, connection.cursor() as cursor:
            evaluation = self._load_evaluation(cursor, evaluation_id)
            try:
                self._verify_prediction_provenance(cursor, evaluation)
            except RegistrationProvenanceError:
                return ("MODEL_INACTIVE_OR_STALE",)
            fixture = self._latest_fixture_observation(cursor, evaluation.fixture_id, checked)
            failures = [
                code.value
                for code in evaluate_persisted_eligibility(
                    evaluation,
                    fixture,
                    policy,
                    decided_at=checked,
                    quote_age_is_warning=True,
                )
            ]
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM registered_picks WHERE fixture_id = %s)",
                (evaluation.fixture_id,),
            )
            if bool(cursor.fetchone()[0]):
                failures.append("DUPLICATE_FIXTURE")
            if policy.fixed_stake_minor > policy.max_stake_per_pick_minor:
                failures.append("STAKE_EXCEEDS_PER_PICK_LIMIT")
            cursor.execute(
                "SELECT balance_after_minor FROM bankroll_ledger_entries "
                "WHERE bankroll_account_id = %s ORDER BY account_sequence DESC LIMIT 1",
                (policy.bankroll_account_id,),
            )
            ledger = cursor.fetchone()
            if ledger is None or int(ledger[0]) < policy.fixed_stake_minor:
                failures.append("INSUFFICIENT_AVAILABLE_BANKROLL")
            cursor.execute(
                "SELECT COALESCE(SUM(-l.amount_minor), 0) FROM bankroll_ledger_entries l "
                "WHERE l.bankroll_account_id = %s AND l.entry_type = 'STAKE_RESERVED' "
                "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events e "
                "WHERE e.pick_id = l.pick_id AND e.outcome IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events successor "
                "WHERE successor.prior_event_id = e.settlement_event_id))",
                (policy.bankroll_account_id,),
            )
            exposure = int(cursor.fetchone()[0])
            if exposure + policy.fixed_stake_minor > policy.max_open_exposure_minor:
                failures.append("MAX_OPEN_EXPOSURE_EXCEEDED")
            return tuple(failures)

    def begin_final_quote_verification(
        self, preliminary_evaluation_id: str, *, requested_at: datetime
    ) -> FinalQuoteClaim:
        requested = _utc(requested_at, "requested_at")
        verification_id = _fact_id("final-quote-verification-v1", preliminary_evaluation_id)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (verification_id,),
            )
            existing = self._load_final_quote_claim(cursor, verification_id)
            if existing is not None:
                if existing.status is FinalQuoteStatus.REQUESTED:
                    cursor.execute(
                        "UPDATE final_quote_verifications SET requested_at = %s "
                        "WHERE verification_id = %s AND status = 'REQUESTED' "
                        "AND requested_at <= %s",
                        (requested, verification_id, requested - timedelta(minutes=5)),
                    )
                    if cursor.rowcount == 1:
                        return FinalQuoteClaim(
                            verification_id,
                            preliminary_evaluation_id,
                            FinalQuoteStatus.REQUESTED,
                            True,
                        )
                return existing
            evaluation = self._load_evaluation(cursor, preliminary_evaluation_id)
            cursor.execute(
                "INSERT INTO final_quote_verifications "
                "(verification_id, preliminary_evaluation_id, fixture_id, market, selection, "
                "bookmaker_id, requested_provider, requested_at, budget_outcome, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'api-football', %s, 'PENDING', 'REQUESTED')",
                (
                    verification_id,
                    evaluation.evaluation_id,
                    evaluation.fixture_id,
                    evaluation.market.value,
                    evaluation.selected_selection.value,
                    evaluation.bookmaker_id,
                    requested,
                ),
            )
            return FinalQuoteClaim(
                verification_id,
                preliminary_evaluation_id,
                FinalQuoteStatus.REQUESTED,
                True,
            )

    def reject_final_quote_verification(
        self,
        verification_id: str,
        *,
        reason_codes: tuple[str, ...],
        budget_outcome: str,
        returned_source: str | None,
        returned_observed_at: datetime | None,
        returned_captured_at: datetime | None,
        quote_age_seconds: float | None,
        decided_at: datetime,
    ) -> FinalQuoteClaim:
        if not reason_codes:
            raise ValueError("final quote rejection requires at least one reason")
        decided = _utc(decided_at, "decided_at")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE final_quote_verifications SET status = 'REJECTED', "
                "budget_outcome = %s, returned_source = %s, returned_observed_at = %s, "
                "returned_captured_at = %s, quote_age_seconds = %s, reason_codes = %s, "
                "decided_at = %s WHERE verification_id = %s AND status = 'REQUESTED'",
                (
                    budget_outcome,
                    returned_source,
                    returned_observed_at,
                    returned_captured_at,
                    quote_age_seconds,
                    list(reason_codes),
                    decided,
                    verification_id,
                ),
            )
            claim = self._load_final_quote_claim(cursor, verification_id)
            if claim is None:
                raise LookupError(f"final quote verification {verification_id!r} does not exist")
            return claim

    def complete_final_quote_verification(
        self,
        verification_id: str,
        final_evaluation_id: str,
        *,
        captured_at: datetime,
        quote_age_seconds: float,
        snapshot_ids: tuple[str, str],
        stale_quote: bool,
        minimum_playable_odds: float,
        decided_at: datetime,
    ) -> FinalQuoteClaim:
        captured = _utc(captured_at, "captured_at")
        decided = _utc(decided_at, "decided_at")
        if len(snapshot_ids) != 2 or len(set(snapshot_ids)) != 2:
            raise ValueError("final verification requires two distinct snapshot IDs")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT preliminary_evaluation_id, fixture_id, market, selection, bookmaker_id "
                "FROM final_quote_verifications WHERE verification_id = %s FOR UPDATE",
                (verification_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"final quote verification {verification_id!r} does not exist")
            existing = self._load_final_quote_claim(cursor, verification_id)
            if existing is not None and existing.status is not FinalQuoteStatus.REQUESTED:
                return existing
            final = self._load_evaluation(cursor, final_evaluation_id)
            preliminary = self._load_evaluation(cursor, row[0])
            if (
                final.fixture_id,
                final.market.value,
                final.selected_selection.value,
                final.bookmaker_id,
                final.prediction_id,
            ) != (
                row[1],
                row[2],
                row[3],
                row[4],
                preliminary.prediction_id,
            ):
                raise RegistrationProvenanceError(
                    "final evaluation does not match preliminary candidate identity"
                )
            cursor.execute(
                "UPDATE final_quote_verifications SET status = 'READY', "
                "budget_outcome = 'ALLOWED', returned_source = %s, "
                "returned_bookmaker_key = %s, returned_observed_at = %s, "
                "returned_captured_at = %s, quote_age_seconds = %s, stale_quote = %s, "
                "warning_codes = %s, returned_snapshot_ids = %s, "
                "final_evaluation_id = %s, final_odd = %s, "
                "final_devig_probability = %s, final_model_probability = %s, "
                "final_edge = %s, final_expected_value = %s, minimum_playable_odds = %s, "
                "reason_codes = '{}', "
                "decided_at = %s WHERE verification_id = %s AND status = 'REQUESTED'",
                (
                    final.source,
                    final.bookmaker_key,
                    final.quote_observed_at,
                    captured,
                    quote_age_seconds,
                    stale_quote,
                    ["STALE_QUOTE_WARNING"] if stale_quote else [],
                    list(snapshot_ids),
                    final.evaluation_id,
                    final.selected_odd,
                    final.selected_devig_probability,
                    final.model_probability,
                    final.edge,
                    final.expected_value,
                    minimum_playable_odds,
                    decided,
                    verification_id,
                ),
            )
            claim = self._load_final_quote_claim(cursor, verification_id)
            if claim is None:
                raise RegistrationProvenanceError("final verification disappeared")
            return claim

    @staticmethod
    def _load_final_quote_claim(cursor: Any, verification_id: str) -> FinalQuoteClaim | None:
        cursor.execute(
            "SELECT verification_id, preliminary_evaluation_id, status, "
            "final_evaluation_id, reason_codes FROM final_quote_verifications "
            "WHERE verification_id = %s",
            (verification_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        status = FinalQuoteStatus(row[2])
        return FinalQuoteClaim(row[0], row[1], status, False, row[3], tuple(row[4]))

    @staticmethod
    def _valid_final_verification(
        cursor: Any, verification_id: str | None, evaluation_id: str
    ) -> bool:
        if verification_id is None:
            return False
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM final_quote_verifications "
            "WHERE verification_id = %s AND status = 'READY' "
            "AND final_evaluation_id = %s)",
            (verification_id, evaluation_id),
        )
        return bool(cursor.fetchone()[0])
        if cursor.fetchone() is None:
            raise RegistrationProvenanceError("prediction/model provenance does not resolve")

    @staticmethod
    def _latest_fixture_observation(cursor: Any, fixture_id: str, decided_at: datetime) -> Any:
        cursor.execute(
            "SELECT fixture_observation_id, fixture_id, home_team, away_team, competition_name, "
            "country, competition_type, kickoff_at, provider_status, source, observed_at, "
            "persisted_at FROM fixture_observations WHERE fixture_id = %s AND observed_at <= %s "
            "AND persisted_at <= %s "
            "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
            (fixture_id, decided_at, decided_at),
        )
        row = cursor.fetchone()
        if row is None:
            raise RegistrationProvenanceError("no fixture observation exists as of decision time")
        return FixtureObservation(*row)

    @staticmethod
    def _persist_policy(
        cursor: Any, policy: RegistrationPolicyConfig, created_at: datetime
    ) -> None:
        cursor.execute(
            "INSERT INTO pick_policy_configurations "
            "(config_fingerprint, schema_version, eligibility_policy_version, "
            "risk_policy_version, staking_policy_version, canonical_configuration, "
            "configuration, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s) "
            "ON CONFLICT DO NOTHING",
            (
                policy.fingerprint,
                policy.schema_version,
                policy.eligibility_policy_version,
                policy.risk_policy_version,
                policy.staking_policy_version,
                policy.canonical_json,
                policy.canonical_json,
                created_at,
            ),
        )
        cursor.execute(
            "SELECT canonical_configuration FROM pick_policy_configurations "
            "WHERE config_fingerprint = %s",
            (policy.fingerprint,),
        )
        row = cursor.fetchone()
        if row is None or row[0] != policy.canonical_json:
            raise RegistrationPersistenceConflictError("policy fingerprint conflicts")

    @staticmethod
    def _insert_decision(
        cursor: Any, decision: PickDecision, final_quote_verification_id: str | None
    ) -> None:
        snapshot, stake = decision.risk_snapshot, decision.stake
        cursor.execute(
            "INSERT INTO pick_decisions "
            "(decision_id, registration_request_id, evaluation_id, fixture_observation_id, "
            "config_fingerprint, decided_at, outcome, rejection_stage, reason_codes, "
            "proposed_stake_minor, currency, bankroll_account_id, "
            "bankroll_reference_entry_id, bankroll_balance_before_minor, "
            "open_exposure_before_minor, final_quote_verification_id) VALUES "
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                decision.decision_id,
                decision.registration_request_id,
                decision.evaluation_id,
                decision.fixture_observation_id,
                decision.policy_config_fingerprint,
                decision.decided_at,
                decision.outcome.value,
                None if decision.rejection_stage is None else decision.rejection_stage.value,
                list(decision.reason_codes),
                None if stake is None else stake.amount_minor,
                None if stake is None else stake.currency,
                None if snapshot is None else snapshot.bankroll_account_id,
                None if snapshot is None else snapshot.reference_ledger_entry_id,
                None if snapshot is None else snapshot.balance_before_minor,
                None if snapshot is None else snapshot.open_exposure_before_minor,
                final_quote_verification_id,
            ),
        )

    @staticmethod
    def _load_result(cursor: Any, request_id: str) -> RegistrationResult | None:
        cursor.execute(
            "SELECT decision_id, registration_request_id, evaluation_id, "
            "fixture_observation_id, config_fingerprint, decided_at, outcome, rejection_stage, "
            "reason_codes, proposed_stake_minor, currency, bankroll_account_id, "
            "bankroll_reference_entry_id, bankroll_balance_before_minor, "
            "open_exposure_before_minor FROM pick_decisions "
            "WHERE registration_request_id = %s",
            (request_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        stake = None if row[9] is None else FixedStakeDecision(int(row[9]), row[10])
        snapshot = None
        if row[11] is not None:
            # Limits come from immutable policy JSON; load them for the domain snapshot.
            cursor.execute(
                "SELECT configuration FROM pick_policy_configurations WHERE config_fingerprint = %s",
                (row[4],),
            )
            configuration = cursor.fetchone()[0]
            if isinstance(configuration, str):
                configuration = json.loads(configuration)
            snapshot = BankrollRiskSnapshot(
                row[11],
                row[12],
                int(row[13]),
                int(row[14]),
                int(configuration["max_stake_per_pick_minor"]),
                int(configuration["max_open_exposure_minor"]),
            )
        decision = PickDecision(
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            DecisionOutcome(row[6]),
            None if row[7] is None else RejectionStage(row[7]),
            tuple(row[8]),
            stake,
            snapshot,
        )
        cursor.execute(
            "SELECT pick_id, decision_id, evaluation_id, fixture_id, market, selection, "
            "entry_snapshot_id, registered_at, stake_minor, currency, bankroll_account_id, "
            "config_fingerprint, initial_state FROM registered_picks WHERE decision_id = %s",
            (decision.decision_id,),
        )
        pick_row = cursor.fetchone()
        pick = None
        if pick_row is not None:
            pick = RegisteredPick(
                pick_row[0],
                pick_row[1],
                pick_row[2],
                pick_row[3],
                Market(pick_row[4]),
                Selection(pick_row[5]),
                pick_row[6],
                pick_row[7],
                int(pick_row[8]),
                pick_row[9],
                pick_row[10],
                pick_row[11],
                PickLifecycleState(pick_row[12]),
            )
        return RegistrationResult(decision, pick)
