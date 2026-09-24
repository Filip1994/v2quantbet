from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.fixture_result import ApiFootballSettlementResultNormalizer
from h2h.domain.pick_monitoring import OddsLifecyclePolicy
from h2h.domain.operator_pick_state import OperatorPickState
from h2h.domain.settlement import ClvAvailability, ResultSettlementPolicy, SettlementOutcome
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_performance import PostgreSQLPerformanceRepository
from h2h.persistence.postgres_pick_monitoring import PostgreSQLPickMonitoringRepository
from h2h.persistence.postgres_pick_registration import PostgreSQLPickRegistrationRepository
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository
from h2h.persistence.operator_pick_state import (
    OperatorPickStateConflictError,
    OperatorPickStateRiskError,
    PostgreSQLOperatorPickStateRepository,
)
from tests.integration.test_postgres_task10_integration import (
    _candidate,
    _cleanup,
    _policy,
)
from tests.integration.test_postgres_task11_integration import (
    _fixture_cutoff,
    _ingest_selected,
)


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MIGRATION_DIR = Path(__file__).parents[2] / "migrations"
RESULT_POLICY = ResultSettlementPolicy()


def _migrate():
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        apply_migrations(connection, MIGRATION_DIR)


def _registered(candidate, account):
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    configured = _policy(account, maximum_quote_age_seconds=7200)
    now = datetime.now(UTC)
    repository.bootstrap_bankroll(configured, occurred_at=now)
    pick = repository.register(
        candidate.evaluation_id, f"task12-{account}", configured, decided_at=now
    ).pick
    assert pick is not None
    return pick


def _payload(candidate, kickoff, *, score=(2, 1), status="FT"):
    provider_id = int(candidate.fixture_id.split(":", 1)[1])
    empty = {"home": None, "away": None}
    return {
        "fixture": {
            "id": provider_id,
            "date": kickoff.isoformat(),
            "status": {"short": status, "long": status},
        },
        "league": {"id": 39, "season": 2024},
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "goals": {"home": score[0], "away": score[1]},
        "score": {
            "halftime": {"home": 1, "away": 0},
            "fulltime": {"home": score[0], "away": score[1]},
            "extratime": empty,
            "penalty": empty,
        },
    }


def _confirm(repository, candidate, kickoff, *, score=(2, 1), start=None):
    first_at = start or kickoff + timedelta(hours=2)
    normalizer = ApiFootballSettlementResultNormalizer()
    first = normalizer.normalize(
        _payload(candidate, kickoff, score=score),
        fixture_id=candidate.fixture_id,
        acquired_at=first_at,
    )
    repository.persist_result(first, checked_at=first_at)
    second_at = first_at + timedelta(seconds=RESULT_POLICY.finality_delay_seconds)
    second = normalizer.normalize(
        _payload(candidate, kickoff, score=score),
        fixture_id=candidate.fixture_id,
        acquired_at=second_at,
    )
    repository.persist_result(second, checked_at=second_at)
    assert second.result_observation_id == first.result_observation_id
    assert (
        repository.stable_result(candidate.fixture_id, as_of=second_at)
        == first.result_observation_id
    )
    return first, second_at


def test_result_settlement_ledger_clv_performance_and_replay() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task12-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLResultSettlementRepository(RESULT_POLICY, database_url=DATABASE_URL)
    cutoff = _fixture_cutoff(candidate)
    try:
        monitor = PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL)
        monitor.start(
            pick.pick_id, OddsLifecyclePolicy(300, 600, 900), started_at=pick.registered_at
        )
        closing_id = _ingest_selected(
            candidate,
            observed_at=cutoff - timedelta(minutes=5),
            captured_at=cutoff - timedelta(minutes=5),
            odd=1.8,
        )
        finalized = monitor.finalize(pick.pick_id, finalized_at=cutoff)
        assert finalized.closing_snapshot_id == closing_id

        repository.reconcile(reconciled_at=cutoff)
        result, settled_at = _confirm(repository, candidate, cutoff)
        with ThreadPoolExecutor(max_workers=2) as executor:
            records = list(
                executor.map(
                    lambda _: PostgreSQLResultSettlementRepository(
                        RESULT_POLICY, database_url=DATABASE_URL
                    ).settle_pick(
                        pick.pick_id, result.result_observation_id, settled_at=settled_at
                    ),
                    range(2),
                )
            )
        assert records[0] == records[1]
        assert records[0].outcome is SettlementOutcome.WIN
        assert records[0].gross_return_minor == pick.stake_minor * 2
        assert records[0].realized_pnl_minor == pick.stake_minor

        clv = repository.finalize_clv(pick.pick_id, realized_at=settled_at)
        assert clv.status is ClvAvailability.AVAILABLE
        assert clv.clv_ppm == 111_111
        assert repository.finalize_clv(pick.pick_id, realized_at=settled_at) == clv

        performance = PostgreSQLPerformanceRepository(database_url=DATABASE_URL).summary(account)
        assert (
            performance.available_bankroll_minor
            == _policy(account).initial_bankroll_minor + pick.stake_minor
        )
        assert performance.open_exposure_minor == 0
        assert performance.equity_at_cost_minor == performance.available_bankroll_minor
        assert performance.realized_pnl_minor == pick.stake_minor
        assert performance.win_count == 1
        assert performance.realized_roi == Decimal(1)

        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT entry_type, amount_minor FROM bankroll_ledger_entries "
                "WHERE pick_id = %s ORDER BY account_sequence",
                (pick.pick_id,),
            )
            assert cursor.fetchall() == [
                ("STAKE_RESERVED", -pick.stake_minor),
                ("PAYOUT", 2 * pick.stake_minor),
            ]
            cursor.execute(
                "SELECT COUNT(*) FROM pick_settlement_events WHERE pick_id = %s", (pick.pick_id,)
            )
            assert cursor.fetchone()[0] == 1
            with pytest.raises(psycopg.errors.RaiseException):
                cursor.execute(
                    "UPDATE bankroll_ledger_entries SET amount_minor = 1 WHERE pick_id = %s",
                    (pick.pick_id,),
                )
    finally:
        _cleanup(account, (candidate,))


def test_operator_state_defaults_played_and_excludes_skipped_from_actual_finances() -> None:
    _migrate()
    candidate = _candidate()
    account = f"operator-{uuid4()}"
    pick = _registered(candidate, account)
    settlement = PostgreSQLResultSettlementRepository(RESULT_POLICY, database_url=DATABASE_URL)
    operator = PostgreSQLOperatorPickStateRepository(database_url=DATABASE_URL)
    cutoff = _fixture_cutoff(candidate)

    settlement.reconcile(reconciled_at=cutoff)
    result, settled_at = _confirm(settlement, candidate, cutoff)
    settlement.settle_pick(pick.pick_id, result.result_observation_id, settled_at=settled_at)
    performance = PostgreSQLPerformanceRepository(database_url=DATABASE_URL)

    assert operator.current_state(pick.pick_id) is OperatorPickState.PLAYED
    assert operator.resolve_short_pick_id(pick.pick_id[-10:]) == pick.pick_id
    actual_played = performance.operator_summary(account)
    system_before = performance.summary(account)
    assert actual_played.realized_pnl_minor == pick.stake_minor
    assert actual_played.total_staked_minor == pick.stake_minor

    skip_request = f"skip-{pick.pick_id}"
    restore_request = f"restore-{pick.pick_id}"
    skipped = operator.set_state(
        pick.pick_id, OperatorPickState.SKIPPED, skip_request, occurred_at=settled_at
    )
    assert (
        operator.set_state(
            pick.pick_id, OperatorPickState.SKIPPED, skip_request, occurred_at=settled_at
        )
        == skipped
    )
    actual_skipped = performance.operator_summary(account)
    system_after = performance.summary(account)
    assert actual_skipped.realized_pnl_minor == 0
    assert actual_skipped.total_staked_minor == 0
    assert actual_skipped.available_bankroll_minor == _policy(account).initial_bankroll_minor
    assert system_after.realized_pnl_minor == system_before.realized_pnl_minor
    assert system_after.win_count == system_before.win_count == 1

    restored = operator.set_state(
        pick.pick_id,
        OperatorPickState.PLAYED,
        restore_request,
        occurred_at=settled_at + timedelta(seconds=1),
    )
    assert restored.state is OperatorPickState.PLAYED
    assert [event.state for event in operator.history(pick.pick_id)] == [
        OperatorPickState.SKIPPED,
        OperatorPickState.PLAYED,
    ]
    assert performance.operator_summary(account).realized_pnl_minor == pick.stake_minor

    with pytest.raises(OperatorPickStateConflictError):
        operator.set_state(
            pick.pick_id, OperatorPickState.PLAYED, skip_request, occurred_at=settled_at
        )
    with pytest.raises(LookupError):
        operator.current_state("registered-pick-v1:" + "0" * 64)

    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM registered_picks WHERE pick_id = %s", (pick.pick_id,))
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'pick_operator_state_events'"
        )
        columns = {row[0] for row in cursor.fetchall()}
        assert "reason" not in columns
        assert "bookmaker_id" not in columns


def test_skipped_pending_pick_releases_only_operator_exposure() -> None:
    _migrate()
    candidate = _candidate()
    account = f"operator-pending-{uuid4()}"
    pick = _registered(candidate, account)
    performance = PostgreSQLPerformanceRepository(database_url=DATABASE_URL)
    operator = PostgreSQLOperatorPickStateRepository(database_url=DATABASE_URL)

    played = performance.operator_summary(account)
    assert played.open_exposure_minor == pick.stake_minor
    assert (
        played.available_bankroll_minor
        == _policy(account).initial_bankroll_minor - pick.stake_minor
    )

    operator.set_state(
        pick.pick_id,
        OperatorPickState.SKIPPED,
        f"skip-pending-{pick.pick_id}",
        occurred_at=datetime.now(UTC),
    )
    skipped = performance.operator_summary(account)
    system = performance.summary(account)
    assert skipped.open_exposure_minor == 0
    assert skipped.available_bankroll_minor == _policy(account).initial_bankroll_minor
    assert system.open_exposure_minor == pick.stake_minor


def test_skipped_pending_pick_releases_registration_risk_capacity() -> None:
    _migrate()
    first_candidate = _candidate()
    second_candidate = _candidate()
    account = f"operator-risk-{uuid4()}"
    configured = _policy(
        account,
        maximum_quote_age_seconds=7200,
        max_open_exposure_minor=30_000,
    )
    registration = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    operator = PostgreSQLOperatorPickStateRepository(database_url=DATABASE_URL)
    now = datetime.now(UTC)
    try:
        registration.bootstrap_bankroll(configured, occurred_at=now)
        first = registration.register(
            first_candidate.evaluation_id,
            f"first-{account}",
            configured,
            decided_at=now,
        ).pick
        assert first is not None

        operator.set_state(
            first.pick_id,
            OperatorPickState.SKIPPED,
            f"skip-{first.pick_id}",
            occurred_at=now + timedelta(seconds=1),
        )
        released = registration.risk_exposure_breakdown(
            account, checked_at=now + timedelta(seconds=1)
        )
        assert released["open_exposure_minor"] == 0
        assert released["risk_reserved_played_minor"] == 0
        assert released["risk_reserved_skipped_minor"] == first.stake_minor

        second = registration.register(
            second_candidate.evaluation_id,
            f"second-{account}",
            configured,
            decided_at=now + timedelta(seconds=2),
        ).pick
        assert second is not None
        after_second = registration.risk_exposure_breakdown(
            account, checked_at=now + timedelta(seconds=2)
        )
        assert after_second["open_exposure_minor"] == second.stake_minor

        with pytest.raises(OperatorPickStateRiskError, match="maximum open exposure"):
            operator.set_state(
                first.pick_id,
                OperatorPickState.PLAYED,
                f"restore-{first.pick_id}",
                occurred_at=now + timedelta(seconds=3),
                max_open_exposure_minor=configured.max_open_exposure_minor,
            )
        assert operator.current_state(first.pick_id) is OperatorPickState.SKIPPED
    finally:
        _cleanup(account, (first_candidate, second_candidate))


def test_registration_and_played_reactivation_share_one_hard_exposure_lock() -> None:
    _migrate()
    first_candidate = _candidate()
    second_candidate = _candidate()
    account = f"operator-risk-race-{uuid4()}"
    configured = _policy(
        account,
        maximum_quote_age_seconds=7200,
        max_open_exposure_minor=30_000,
    )
    registration = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    operator = PostgreSQLOperatorPickStateRepository(database_url=DATABASE_URL)
    now = datetime.now(UTC)
    try:
        registration.bootstrap_bankroll(configured, occurred_at=now)
        first = registration.register(
            first_candidate.evaluation_id,
            f"first-race-{account}",
            configured,
            decided_at=now,
        ).pick
        assert first is not None
        operator.set_state(
            first.pick_id,
            OperatorPickState.SKIPPED,
            f"skip-race-{first.pick_id}",
            occurred_at=now + timedelta(seconds=1),
        )

        barrier = Barrier(2)

        def reactivate() -> str:
            barrier.wait()
            try:
                PostgreSQLOperatorPickStateRepository(
                    database_url=DATABASE_URL
                ).set_state(
                    first.pick_id,
                    OperatorPickState.PLAYED,
                    f"restore-race-{first.pick_id}",
                    occurred_at=now + timedelta(seconds=2),
                    max_open_exposure_minor=configured.max_open_exposure_minor,
                )
            except OperatorPickStateRiskError:
                return "reactivation_blocked"
            return "reactivated"

        def register_second() -> str:
            barrier.wait()
            result = PostgreSQLPickRegistrationRepository(
                database_url=DATABASE_URL
            ).register(
                second_candidate.evaluation_id,
                f"second-race-{account}",
                configured,
                decided_at=now + timedelta(seconds=2),
            )
            return "registered" if result.pick is not None else "registration_blocked"

        with ThreadPoolExecutor(max_workers=2) as executor:
            restore_future = executor.submit(reactivate)
            register_future = executor.submit(register_second)
            outcomes = {restore_future.result(), register_future.result()}

        assert outcomes in (
            {"reactivated", "registration_blocked"},
            {"reactivation_blocked", "registered"},
        )
        snapshot = registration.risk_exposure_breakdown(
            account, checked_at=now + timedelta(seconds=3)
        )
        assert snapshot["open_exposure_minor"] == 30_000
        assert snapshot["risk_reserved_played_count"] == 1
    finally:
        _cleanup(account, (first_candidate, second_candidate))


@pytest.mark.parametrize(
    ("status", "score", "entry_type", "amount_factor", "pnl_factor"),
    [
        ("FT", (1, 0), "LOSS", 0, -1),
        ("CANC", (None, None), "VOID_REFUND", 1, 0),
    ],
)
def test_loss_and_void_release_reservation(status, score, entry_type, amount_factor, pnl_factor):
    _migrate()
    candidate = _candidate()
    account = f"task12-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLResultSettlementRepository(RESULT_POLICY, database_url=DATABASE_URL)
    kickoff = _fixture_cutoff(candidate)
    try:
        repository.reconcile(reconciled_at=kickoff)
        first_at = kickoff + timedelta(hours=2)
        normalizer = ApiFootballSettlementResultNormalizer()
        payload = _payload(candidate, kickoff, score=score, status=status)
        first = normalizer.normalize(payload, fixture_id=candidate.fixture_id, acquired_at=first_at)
        repository.persist_result(first, checked_at=first_at)
        second_at = first_at + timedelta(minutes=15)
        replay = normalizer.normalize(
            payload, fixture_id=candidate.fixture_id, acquired_at=second_at
        )
        repository.persist_result(replay, checked_at=second_at)
        settled = repository.settle_pick(
            pick.pick_id, first.result_observation_id, settled_at=second_at
        )
        assert settled.realized_pnl_minor == pnl_factor * pick.stake_minor
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT amount_minor FROM bankroll_ledger_entries "
                "WHERE pick_id = %s AND entry_type = %s",
                (pick.pick_id, entry_type),
            )
            assert cursor.fetchone()[0] == amount_factor * pick.stake_minor
    finally:
        _cleanup(account, (candidate,))


def test_changed_result_requires_correction_without_financial_mutation() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task12-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLResultSettlementRepository(RESULT_POLICY, database_url=DATABASE_URL)
    kickoff = _fixture_cutoff(candidate)
    try:
        repository.reconcile(reconciled_at=kickoff)
        original, settled_at = _confirm(repository, candidate, kickoff, score=(2, 1))
        repository.settle_pick(pick.pick_id, original.result_observation_id, settled_at=settled_at)
        changed_start = settled_at + timedelta(hours=1)
        changed, _ = _confirm(repository, candidate, kickoff, score=(1, 0), start=changed_start)
        assert changed.result_observation_id != original.result_observation_id
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT correction_required, contradicting_observation_id "
                "FROM fixture_result_acquisition_states WHERE fixture_id = %s",
                (candidate.fixture_id,),
            )
            assert cursor.fetchone() == (True, changed.result_observation_id)
            cursor.execute(
                "SELECT COUNT(*) FROM pick_settlement_events WHERE pick_id = %s", (pick.pick_id,)
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT COUNT(*) FROM bankroll_ledger_entries WHERE pick_id = %s", (pick.pick_id,)
            )
            assert cursor.fetchone()[0] == 2
    finally:
        _cleanup(account, (candidate,))
