from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.fixture import Fixture
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.operator_pick_state import OperatorPickState
from h2h.domain.pick_decision import DecisionOutcome, RiskRejectionCode
from h2h.domain.prediction_record import PersistedFixturePrediction
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.pick_registration import (
    BankrollBootstrapConflictError,
    RegistrationPersistenceConflictError,
)
from h2h.persistence.operator_pick_state import PostgreSQLOperatorPickStateRepository
from h2h.persistence.postgres_fixtures import PostgreSQLFixtureRepository
from h2h.persistence.postgres_model_lifecycle import PostgreSQLDixonColesModelVersionRepository
from h2h.persistence.postgres_pick_registration import PostgreSQLPickRegistrationRepository
from h2h.persistence.postgres_predictions import PostgreSQLFixturePredictionRepository
from h2h.persistence.postgres_quote_history import PostgreSQLQuoteHistoryRepository
from h2h.persistence.postgres_value_evaluations import PostgreSQLValueEvaluationRepository
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.value_evaluation import EvaluatePersistedPredictionQuote
from tests.domain.test_task10_policy import policy as base_policy
from tests.quant.test_dixon_coles_artifact import TRAINED_AT, trusted_artifact


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MIGRATION_DIR = Path(__file__).parents[2] / "migrations"
NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


@dataclass
class DurableCandidate:
    fixture_id: str
    prediction_id: str
    evaluation_id: str
    model_version_id: str
    series_ids: tuple[str, ...]
    snapshot_ids: tuple[str, ...]


def _migrate() -> None:
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        apply_migrations(connection, MIGRATION_DIR)


def _candidate(*, selected: Selection = Selection.OVER) -> DurableCandidate:
    assert DATABASE_URL is not None
    observed_at = datetime.now(UTC)
    token = uuid4().int
    provider_fixture_id = str(token % 8_000_000_000 + 1_000_000_000)
    fixture_id = f"api-football:{provider_fixture_id}"
    _, artifact = trusted_artifact(TRAINED_AT + timedelta(seconds=token % 100_000))
    PostgreSQLDixonColesModelVersionRepository(database_url=DATABASE_URL).add(artifact)
    fixture_repo = PostgreSQLFixtureRepository(database_url=DATABASE_URL)
    durable = fixture_repo.record_discovery(
        Fixture(
            fixture_id=fixture_id,
            home_team="Home",
            away_team="Away",
            competition_id=39,
            competition_name="Premier League",
            country="England",
            kickoff_at=observed_at + timedelta(hours=1),
            competition_type="League",
            season=2024,
            status="NS",
            provider="api-football",
            provider_fixture_id=provider_fixture_id,
            provider_home_team_id=1,
            provider_away_team_id=2,
        ),
        observed_at=observed_at,
    )
    quote_repo = PostgreSQLQuoteHistoryRepository(database_url=DATABASE_URL)
    QuoteHistoryIngestionService(quote_repo, capture_clock=lambda: observed_at).ingest(
        (
            CanonicalQuote(
                fixture_id,
                8,
                "Bet365",
                Market.OU_25,
                Selection.OVER,
                2.0,
                observed_at,
                "api-football",
            ),
            CanonicalQuote(
                fixture_id,
                8,
                "Bet365",
                Market.OU_25,
                Selection.UNDER,
                1.8,
                observed_at,
                "api-football",
            ),
        )
    )
    series = quote_repo.series_for_fixture(fixture_id)
    snapshots = {
        item.selection: quote_repo.snapshots_for_series(item.series_id)[0] for item in series
    }
    prediction = PersistedFixturePrediction(
        prediction_id="fixture-prediction-v1:" + f"{token:064x}"[-64:],
        fixture_id=fixture_id,
        fixture_observation_id=durable.observation.fixture_observation_id,
        model_version_id=artifact.model_version_id,
        active_generation=1,
        model_activated_at=TRAINED_AT,
        provider="api-football",
        team_id_namespace="api-football",
        league_id=39,
        season=2024,
        provider_home_team_id=1,
        provider_away_team_id=2,
        prediction_method_version="DIXON_COLES_MARKET_PROBABILITIES_V1",
        max_goals=10,
        over_2_5_probability=0.6 if selected is Selection.OVER else 0.4,
        under_2_5_probability=0.4 if selected is Selection.OVER else 0.6,
        btts_yes_probability=0.55,
        predicted_at=observed_at,
        persisted_at=observed_at,
    )
    predictions = PostgreSQLFixturePredictionRepository(database_url=DATABASE_URL)
    predictions.add(prediction)
    evaluations = PostgreSQLValueEvaluationRepository(database_url=DATABASE_URL)
    evaluation = EvaluatePersistedPredictionQuote(
        predictions, quote_repo, evaluations, clock=lambda: observed_at
    ).execute(prediction.prediction_id, snapshots[selected].snapshot_id)
    return DurableCandidate(
        fixture_id,
        prediction.prediction_id,
        evaluation.evaluation_id,
        artifact.model_version_id,
        tuple(item.series_id for item in series),
        tuple(snapshot.snapshot_id for snapshot in snapshots.values()),
    )


def _second_evaluation(candidate: DurableCandidate) -> str:
    """Create an independently eligible opposite-side evaluation for duplicate testing."""
    assert DATABASE_URL is not None
    token = uuid4().int
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT fixture_observation_id FROM fixture_observations WHERE fixture_id = %s "
            "ORDER BY observed_at DESC LIMIT 1",
            (candidate.fixture_id,),
        )
        observation_id = cursor.fetchone()[0]
        cursor.execute(
            "SELECT snapshot_id FROM quote_snapshots q JOIN quote_series s "
            "ON s.series_id = q.series_id WHERE s.fixture_id = %s AND s.selection = 'UNDER'",
            (candidate.fixture_id,),
        )
        snapshot_id = cursor.fetchone()[0]
    prediction = PersistedFixturePrediction(
        prediction_id="fixture-prediction-v1:" + f"{token:064x}"[-64:],
        fixture_id=candidate.fixture_id,
        fixture_observation_id=observation_id,
        model_version_id=candidate.model_version_id,
        active_generation=2,
        model_activated_at=TRAINED_AT,
        provider="api-football",
        team_id_namespace="api-football",
        league_id=39,
        season=2024,
        provider_home_team_id=1,
        provider_away_team_id=2,
        prediction_method_version="DIXON_COLES_MARKET_PROBABILITIES_V1",
        max_goals=10,
        over_2_5_probability=0.4,
        under_2_5_probability=0.6,
        btts_yes_probability=0.55,
        predicted_at=NOW,
        persisted_at=NOW,
    )
    predictions = PostgreSQLFixturePredictionRepository(database_url=DATABASE_URL)
    predictions.add(prediction)
    return (
        EvaluatePersistedPredictionQuote(
            predictions,
            PostgreSQLQuoteHistoryRepository(database_url=DATABASE_URL),
            PostgreSQLValueEvaluationRepository(database_url=DATABASE_URL),
            clock=lambda: NOW,
        )
        .execute(prediction.prediction_id, snapshot_id)
        .evaluation_id
    )


def _btts_evaluation(candidate: DurableCandidate) -> str:
    """Create an independently eligible BTTS evaluation on the same fixture."""
    assert DATABASE_URL is not None
    observed_at = datetime.now(UTC)
    token = uuid4().int
    quote_repo = PostgreSQLQuoteHistoryRepository(database_url=DATABASE_URL)
    QuoteHistoryIngestionService(quote_repo, capture_clock=lambda: observed_at).ingest(
        (
            CanonicalQuote(
                candidate.fixture_id,
                8,
                "Bet365",
                Market.BTTS,
                Selection.YES,
                1.7,
                observed_at,
                "api-football",
            ),
            CanonicalQuote(
                candidate.fixture_id,
                8,
                "Bet365",
                Market.BTTS,
                Selection.NO,
                2.2,
                observed_at,
                "api-football",
            ),
        )
    )
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT fixture_observation_id FROM fixture_observations WHERE fixture_id = %s "
            "ORDER BY observed_at DESC LIMIT 1",
            (candidate.fixture_id,),
        )
        observation_id = cursor.fetchone()[0]
        cursor.execute(
            "SELECT q.snapshot_id FROM quote_snapshots q JOIN quote_series s "
            "ON s.series_id = q.series_id WHERE s.fixture_id = %s "
            "AND s.market = 'BTTS' AND s.selection = 'NO' "
            "ORDER BY q.captured_at DESC LIMIT 1",
            (candidate.fixture_id,),
        )
        snapshot_id = cursor.fetchone()[0]
    prediction = PersistedFixturePrediction(
        prediction_id="fixture-prediction-v1:" + f"{token:064x}"[-64:],
        fixture_id=candidate.fixture_id,
        fixture_observation_id=observation_id,
        model_version_id=candidate.model_version_id,
        active_generation=2,
        model_activated_at=TRAINED_AT,
        provider="api-football",
        team_id_namespace="api-football",
        league_id=39,
        season=2024,
        provider_home_team_id=1,
        provider_away_team_id=2,
        prediction_method_version="DIXON_COLES_MARKET_PROBABILITIES_V1",
        max_goals=10,
        over_2_5_probability=0.5,
        under_2_5_probability=0.5,
        btts_yes_probability=0.4,
        predicted_at=observed_at,
        persisted_at=observed_at,
    )
    predictions = PostgreSQLFixturePredictionRepository(database_url=DATABASE_URL)
    predictions.add(prediction)
    return (
        EvaluatePersistedPredictionQuote(
            predictions,
            quote_repo,
            PostgreSQLValueEvaluationRepository(database_url=DATABASE_URL),
            clock=lambda: observed_at,
        )
        .execute(prediction.prediction_id, snapshot_id)
        .evaluation_id
    )


def _policy(account_id: str, **changes):
    return replace(
        base_policy(),
        bankroll_account_id=account_id,
        allowed_fixture_statuses=("NS",),
        **changes,
    )


def _cleanup(account_id: str, candidates: tuple[DurableCandidate, ...]) -> None:
    assert DATABASE_URL is not None
    fixture_ids = [item.fixture_id for item in candidates]
    model_ids = [item.model_version_id for item in candidates]
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE research_fixture_result_finalizations, research_signals, "
            "pick_operator_state_events, daily_bulletin_memberships, daily_bulletins, "
            "pick_realized_clv, pick_settlement_events, "
            "fixture_result_acquisition_states, fixture_result_observations, "
            "pick_manual_closing_overrides, "
            "pick_live_close_finalizations, pick_live_close_observations, "
            "pick_closing_finalizations, pick_monitoring_transitions, "
            "pick_monitoring_states, registered_picks, pick_decisions, "
            "final_quote_verifications, bankroll_ledger_entries, "
            "bankroll_accounts, pick_policy_configurations"
        )
        cursor.execute("DELETE FROM value_evaluations WHERE fixture_id = ANY(%s)", (fixture_ids,))
        cursor.execute("DELETE FROM fixture_predictions WHERE fixture_id = ANY(%s)", (fixture_ids,))
        cursor.execute(
            "DELETE FROM quote_snapshots WHERE series_id IN "
            "(SELECT series_id FROM quote_series WHERE fixture_id = ANY(%s))",
            (fixture_ids,),
        )
        cursor.execute("DELETE FROM quote_series WHERE fixture_id = ANY(%s)", (fixture_ids,))
        cursor.execute(
            "DELETE FROM fixture_observations WHERE fixture_id = ANY(%s)", (fixture_ids,)
        )
        cursor.execute("DELETE FROM fixtures WHERE fixture_id = ANY(%s)", (fixture_ids,))
        cursor.execute(
            "DELETE FROM dixon_coles_model_versions WHERE model_version_id = ANY(%s) "
            "AND NOT EXISTS (SELECT 1 FROM dixon_coles_active_models a "
            "WHERE a.model_version_id = dixon_coles_model_versions.model_version_id)",
            (model_ids,),
        )


def test_concurrent_identical_registration_request_is_idempotent() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task10-{uuid4()}"
    configured = _policy(account)
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    try:
        repository.bootstrap_bankroll(configured, occurred_at=NOW)
        decision_at = datetime.now(UTC)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: PostgreSQLPickRegistrationRepository(
                        database_url=DATABASE_URL
                    ).register(
                        candidate.evaluation_id,
                        "same-" + account,
                        configured,
                        decided_at=decision_at,
                    ),
                    range(2),
                )
            )
        assert results[0] == results[1]
        assert results[0].decision.outcome is DecisionOutcome.APPROVED
    finally:
        _cleanup(account, (candidate,))


def test_bankroll_bootstrap_idempotency_conflict_and_restart_reconstruction() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task10-{uuid4()}"
    configured = _policy(account)
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    try:
        first = repository.bootstrap_bankroll(configured, occurred_at=NOW)
        assert (
            repository.bootstrap_bankroll(configured, occurred_at=NOW + timedelta(seconds=1))
            == first
        )
        with pytest.raises(BankrollBootstrapConflictError):
            repository.bootstrap_bankroll(
                replace(configured, initial_bankroll_minor=2_000_000),
                occurred_at=NOW,
            )
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO pick_policy_configurations "
                "(config_fingerprint, schema_version, eligibility_policy_version, "
                "risk_policy_version, staking_policy_version, canonical_configuration, "
                "configuration) VALUES (%s, 1, %s, %s, %s, '{}', '{}'::jsonb)",
                (
                    configured.fingerprint,
                    configured.eligibility_policy_version,
                    configured.risk_policy_version,
                    configured.staking_policy_version,
                ),
            )
        with pytest.raises(RegistrationPersistenceConflictError, match="fingerprint"):
            repository.register(
                candidate.evaluation_id,
                "policy-conflict-" + account,
                configured,
                decided_at=datetime.now(UTC),
            )
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM pick_policy_configurations WHERE config_fingerprint = %s",
                (configured.fingerprint,),
            )
        decision_at = datetime.now(UTC)
        result = repository.register(
            candidate.evaluation_id,
            "restart-" + account,
            configured,
            decided_at=decision_at,
        )
        replay = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL).register(
            candidate.evaluation_id,
            "restart-" + account,
            configured,
            decided_at=decision_at + timedelta(seconds=1),
        )
        assert replay == result
        second_evaluation_id = _second_evaluation(candidate)
        with pytest.raises(RegistrationPersistenceConflictError, match="different input"):
            repository.register(
                second_evaluation_id,
                "restart-" + account,
                configured,
                decided_at=datetime.now(UTC),
            )
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT balance_after_minor FROM bankroll_ledger_entries "
                "WHERE bankroll_account_id = %s ORDER BY account_sequence",
                (account,),
            )
            assert [row[0] for row in cursor.fetchall()] == [3_000_000, 2_970_000]
            cursor.execute(
                "SELECT COUNT(*) FROM pick_decisions WHERE registration_request_id = %s",
                ("restart-" + account,),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT r.entry_snapshot_id, e.selected_snapshot_id "
                "FROM registered_picks r JOIN value_evaluations e "
                "ON e.evaluation_id = r.evaluation_id WHERE r.evaluation_id = %s",
                (candidate.evaluation_id,),
            )
            assert cursor.fetchone() == (
                result.pick.entry_snapshot_id,
                result.pick.entry_snapshot_id,
            )
        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation),
            psycopg.connect(DATABASE_URL) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE registered_picks SET entry_snapshot_id = "
                "(SELECT companion_snapshot_id FROM value_evaluations WHERE evaluation_id = %s) "
                "WHERE evaluation_id = %s",
                (candidate.evaluation_id, candidate.evaluation_id),
            )
    finally:
        _cleanup(account, (candidate,))


def test_concurrent_different_evaluations_same_fixture_market_register_once() -> None:
    _migrate()
    candidate = _candidate()
    second_evaluation_id = _second_evaluation(candidate)
    account = f"task10-{uuid4()}"
    configured = _policy(account)
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    try:
        repository.bootstrap_bankroll(configured, occurred_at=NOW)
        decision_at = datetime.now(UTC)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL).register,
                    evaluation_id,
                    f"request-{evaluation_id}",
                    configured,
                    decided_at=decision_at,
                )
                for evaluation_id in (candidate.evaluation_id, second_evaluation_id)
            ]
            results = [future.result() for future in futures]
        assert sum(result.pick is not None for result in results) == 1
        rejected = next(result for result in results if result.pick is None)
        assert RiskRejectionCode.DUPLICATE_FIXTURE.value in rejected.decision.reason_codes
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT (SELECT COUNT(*) FROM pick_decisions), "
                "(SELECT COUNT(*) FROM registered_picks), "
                "(SELECT COUNT(*) FROM bankroll_ledger_entries "
                "WHERE entry_type = 'STAKE_RESERVED')"
            )
            assert cursor.fetchone() == (2, 1, 1)
    finally:
        _cleanup(account, (candidate,))


def test_different_markets_on_same_fixture_register_only_one_pick() -> None:
    _migrate()
    candidate = _candidate()
    btts_evaluation_id = _btts_evaluation(candidate)
    account = f"task10-{uuid4()}"
    configured = _policy(account)
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    try:
        repository.bootstrap_bankroll(configured, occurred_at=NOW)
        first = repository.register(
            candidate.evaluation_id,
            "ou-" + account,
            configured,
            decided_at=datetime.now(UTC),
        )
        second = repository.register(
            btts_evaluation_id,
            "btts-" + account,
            configured,
            decided_at=datetime.now(UTC),
        )

        assert first.pick is not None
        assert second.pick is None
        assert RiskRejectionCode.DUPLICATE_FIXTURE.value in second.decision.reason_codes
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM registered_picks WHERE fixture_id = %s",
                (candidate.fixture_id,),
            )
            assert cursor.fetchone()[0] == 1
    finally:
        _cleanup(account, (candidate,))


@pytest.mark.parametrize(
    ("initial", "max_exposure", "expected_code"),
    [
        (30_000, 60_000, RiskRejectionCode.INSUFFICIENT_AVAILABLE_BANKROLL),
        (100_000, 30_000, RiskRejectionCode.MAX_OPEN_EXPOSURE_EXCEEDED),
    ],
)
def test_concurrent_bankroll_consumers_respect_balance_and_exposure(
    initial, max_exposure, expected_code
) -> None:
    _migrate()
    candidates = (_candidate(), _candidate())
    account = f"task10-{uuid4()}"
    configured = _policy(
        account,
        initial_bankroll_minor=initial,
        max_open_exposure_minor=max_exposure,
    )
    PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL).bootstrap_bankroll(
        configured, occurred_at=NOW
    )
    try:
        decision_at = datetime.now(UTC)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL).register,
                    candidate.evaluation_id,
                    f"request-{candidate.evaluation_id}",
                    configured,
                    decided_at=decision_at,
                )
                for candidate in candidates
            ]
            results = [future.result() for future in futures]
        assert sum(result.pick is not None for result in results) == 1
        rejected = next(result for result in results if result.pick is None)
        assert expected_code.value in rejected.decision.reason_codes
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT (SELECT COUNT(*) FROM registered_picks), "
                "(SELECT COUNT(*) FROM bankroll_ledger_entries "
                "WHERE entry_type = 'STAKE_RESERVED')"
            )
            assert cursor.fetchone() == (1, 1)
    finally:
        _cleanup(account, candidates)


def test_transaction_failure_leaves_no_partial_decision_pick_or_reservation() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task10-{uuid4()}"
    configured = _policy(account)

    class FailingRepository(PostgreSQLPickRegistrationRepository):
        def _after_pick_insert(self, cursor, pick):
            raise RuntimeError("injected failure")

    repository = FailingRepository(database_url=DATABASE_URL)
    try:
        repository.bootstrap_bankroll(configured, occurred_at=NOW)
        rejected = repository.register(
            candidate.evaluation_id,
            "eligibility-rejection-" + account,
            replace(configured, minimum_edge=Decimal(1)),
            decided_at=datetime.now(UTC),
        )
        assert rejected.decision.outcome is DecisionOutcome.REJECTED
        assert rejected.pick is None
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT (SELECT COUNT(*) FROM registered_picks), "
                "(SELECT COUNT(*) FROM bankroll_ledger_entries "
                "WHERE entry_type = 'STAKE_RESERVED')"
            )
            assert cursor.fetchone() == (0, 0)
        decision_at = datetime.now(UTC)
        with pytest.raises(RuntimeError, match="injected failure"):
            repository.register(
                candidate.evaluation_id,
                "failure-" + account,
                configured,
                decided_at=decision_at,
            )
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM pick_decisions WHERE registration_request_id = %s",
                ("failure-" + account,),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT COUNT(*) FROM registered_picks WHERE evaluation_id = %s",
                (candidate.evaluation_id,),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT COUNT(*) FROM bankroll_ledger_entries WHERE bankroll_account_id = %s "
                "AND entry_type = 'STAKE_RESERVED'",
                (account,),
            )
            assert cursor.fetchone()[0] == 0
    finally:
        _cleanup(account, (candidate,))


def test_complete_migration_chain_reaches_task10() -> None:
    _migrate()
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        versions = {row[0] for row in cursor.fetchall()}
    assert {
        "001_quote_history.sql",
        "002_quote_snapshot_observation_identity.sql",
        "003_dixon_coles_model_lifecycle.sql",
        "004_fixture_prediction_value_evaluation.sql",
        "005_pick_decision_risk_registration.sql",
    } <= versions



def test_skipped_pick_releases_registration_exposure_without_rewriting_ledger() -> None:
    _migrate()
    first = _candidate()
    second = _candidate()
    account = f"task10-skipped-risk-{uuid4()}"
    configured = _policy(account, max_open_exposure_minor=30_000)
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    operator = PostgreSQLOperatorPickStateRepository(database_url=DATABASE_URL)
    try:
        now = datetime.now(UTC)
        repository.bootstrap_bankroll(configured, occurred_at=now)
        first_result = repository.register(
            first.evaluation_id,
            f"first-{account}",
            configured,
            decided_at=now,
        )
        assert first_result.pick is not None

        before = repository.risk_exposure_breakdown(account, checked_at=now)
        assert before["open_exposure_minor"] == 30_000
        assert before["risk_reserved_pick_count"] == 1
        assert before["risk_reserved_played_count"] == 1
        assert before["risk_reserved_skipped_count"] == 0
        assert "MAX_OPEN_EXPOSURE_EXCEEDED" in repository.preliminary_rejection_codes(
            second.evaluation_id,
            configured,
            checked_at=now,
        )

        operator.set_state(
            first_result.pick.pick_id,
            OperatorPickState.SKIPPED,
            f"skip-{account}",
            occurred_at=now + timedelta(seconds=1),
        )

        after = repository.risk_exposure_breakdown(
            account,
            checked_at=now + timedelta(seconds=1),
        )
        assert after["open_exposure_minor"] == 0
        assert after["risk_reserved_pick_count"] == 1
        assert after["risk_reserved_played_count"] == 0
        assert after["risk_reserved_skipped_count"] == 1
        assert after["risk_reserved_skipped_minor"] == 30_000

        rejection_codes = repository.preliminary_rejection_codes(
            second.evaluation_id,
            configured,
            checked_at=now + timedelta(seconds=1),
        )
        assert "MAX_OPEN_EXPOSURE_EXCEEDED" not in rejection_codes

        second_result = repository.register(
            second.evaluation_id,
            f"second-{account}",
            configured,
            decided_at=now + timedelta(seconds=1),
        )
        assert second_result.pick is not None
        assert second_result.decision.outcome is DecisionOutcome.APPROVED

        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM bankroll_ledger_entries "
                "WHERE bankroll_account_id = %s AND entry_type = 'STAKE_RESERVED'",
                (account,),
            )
            assert cursor.fetchone()[0] == 2
    finally:
        _cleanup(account, (first, second))