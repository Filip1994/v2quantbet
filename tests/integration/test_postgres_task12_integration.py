from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.fixture_result import ApiFootballSettlementResultNormalizer
from h2h.domain.pick_monitoring import OddsLifecyclePolicy
from h2h.domain.settlement import ClvAvailability, ResultSettlementPolicy, SettlementOutcome
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_performance import PostgreSQLPerformanceRepository
from h2h.persistence.postgres_pick_monitoring import PostgreSQLPickMonitoringRepository
from h2h.persistence.postgres_pick_registration import PostgreSQLPickRegistrationRepository
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository
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
    assert repository.stable_result(candidate.fixture_id, as_of=second_at) == first.result_observation_id
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
        monitor.start(pick.pick_id, OddsLifecyclePolicy(300, 600, 900), started_at=pick.registered_at)
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
        assert performance.available_bankroll_minor == _policy(account).initial_bankroll_minor + pick.stake_minor
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
            assert cursor.fetchall() == [("STAKE_RESERVED", -pick.stake_minor), ("PAYOUT", 2 * pick.stake_minor)]
            cursor.execute("SELECT COUNT(*) FROM pick_settlement_events WHERE pick_id = %s", (pick.pick_id,))
            assert cursor.fetchone()[0] == 1
            with pytest.raises(psycopg.errors.RaiseException):
                cursor.execute(
                    "UPDATE bankroll_ledger_entries SET amount_minor = 1 WHERE pick_id = %s",
                    (pick.pick_id,),
                )
    finally:
        _cleanup(account, (candidate,))


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
        replay = normalizer.normalize(payload, fixture_id=candidate.fixture_id, acquired_at=second_at)
        repository.persist_result(replay, checked_at=second_at)
        settled = repository.settle_pick(pick.pick_id, first.result_observation_id, settled_at=second_at)
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
        changed, _ = _confirm(
            repository, candidate, kickoff, score=(1, 0), start=changed_start
        )
        assert changed.result_observation_id != original.result_observation_id
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT correction_required, contradicting_observation_id "
                "FROM fixture_result_acquisition_states WHERE fixture_id = %s",
                (candidate.fixture_id,),
            )
            assert cursor.fetchone() == (True, changed.result_observation_id)
            cursor.execute("SELECT COUNT(*) FROM pick_settlement_events WHERE pick_id = %s", (pick.pick_id,))
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT COUNT(*) FROM bankroll_ledger_entries WHERE pick_id = %s", (pick.pick_id,))
            assert cursor.fetchone()[0] == 2
    finally:
        _cleanup(account, (candidate,))
