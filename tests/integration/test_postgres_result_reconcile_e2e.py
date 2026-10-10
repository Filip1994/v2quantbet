"""End-to-end result reconciliation with one quarantined and one settled pick."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest

from h2h.domain.settlement import ResultSettlementPolicy
from h2h.persistence.postgres_performance import PostgreSQLPerformanceRepository
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository
from h2h.production import ProviderOperationalState
from h2h.use_cases.result_settlement import ReconcileFixtureResults
from tests.integration.test_postgres_task10_integration import _candidate, _cleanup, _migrate
from tests.integration.test_postgres_task11_integration import _fixture_cutoff
from tests.integration.test_postgres_task12_integration import _payload, _registered


psycopg = pytest.importorskip("psycopg")
DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="isolated PostgreSQL required")


class Source:
    def __init__(self, payloads):
        self.payloads = payloads
        self.fetched = []

    def fetch(self, contexts):
        fixture_id, _ = contexts[0]
        self.fetched.append(fixture_id)
        return {fixture_id: self.payloads[fixture_id]}


def test_disputed_pick_stays_unsettled_while_valid_pick_settles() -> None:
    assert DATABASE_URL is not None
    _migrate()
    disputed, valid = sorted((_candidate(), _candidate()), key=lambda item: item.fixture_id)
    disputed_account = f"disputed-{uuid4()}"
    valid_account = f"valid-{uuid4()}"
    runtime = PostgreSQLRuntimeRepository(database_url=DATABASE_URL)
    repository = PostgreSQLResultSettlementRepository(
        ResultSettlementPolicy(), database_url=DATABASE_URL
    )
    provider_state = ProviderOperationalState()
    disputed_pick = _registered(disputed, disputed_account)
    valid_pick = _registered(valid, valid_account)
    assert disputed_pick is not None and valid_pick is not None
    first_at = max(_fixture_cutoff(disputed), _fixture_cutoff(valid)) + timedelta(hours=2)
    current = [first_at]
    bad_payload = _payload(disputed, _fixture_cutoff(disputed))
    bad_payload["teams"]["home"]["id"] = 2
    bad_payload["teams"]["away"]["id"] = 1
    source = Source({
        disputed.fixture_id: bad_payload,
        valid.fixture_id: _payload(valid, _fixture_cutoff(valid)),
    })

    def record_failure(fixture_id, error, at):
        provider_state.failure(error, at=at)
        runtime.record_item_failure("results", fixture_id, error, failed_at=at)

    reconcile = ReconcileFixtureResults(
        repository,
        source,  # type: ignore[arg-type]
        clock=lambda: current[0],
        on_item_failure=record_failure,
        on_item_success=lambda fixture_id: runtime.clear_item_failure("results", fixture_id),
    )
    try:
        first = reconcile.execute()
        assert set(first.claimed_fixture_ids) == {disputed.fixture_id, valid.fixture_id}
        assert source.fetched == [disputed.fixture_id, valid.fixture_id]
        assert first.persisted_result_count == 1
        assert first.settled_pick_ids == ()
        assert provider_state.last_error_class == "ResultPersistenceConflictError"
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM fixture_result_observations WHERE fixture_id = %s",
                (disputed.fixture_id,),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT failure_count, last_error_class FROM production_item_failures "
                "WHERE worker_name = 'results' AND item_id = %s", (disputed.fixture_id,)
            )
            assert cursor.fetchone() == (1, "ResultPersistenceConflictError")
            cursor.execute(
                "SELECT count(*) FROM pick_settlement_events WHERE pick_id = %s",
                (disputed_pick.pick_id,),
            )
            assert cursor.fetchone()[0] == 0
        assert runtime.readiness_snapshot()[1]["result_conflicts"] == 1

        current[0] += timedelta(seconds=repository.policy.finality_delay_seconds)
        second = reconcile.execute()
        assert second.claimed_fixture_ids == (valid.fixture_id,)
        assert source.fetched.count(disputed.fixture_id) == 1
        assert second.settled_pick_ids == (valid_pick.pick_id,)
        assert second.persisted_result_count == 1
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pick_settlement_events WHERE pick_id = %s",
                (valid_pick.pick_id,),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT entry_type, amount_minor FROM bankroll_ledger_entries "
                "WHERE pick_id = %s ORDER BY account_sequence", (valid_pick.pick_id,)
            )
            assert cursor.fetchall() == [
                ("STAKE_RESERVED", -valid_pick.stake_minor),
                ("PAYOUT", 2 * valid_pick.stake_minor),
            ]
            cursor.execute(
                "SELECT count(*) FROM pick_settlement_events WHERE pick_id = %s",
                (disputed_pick.pick_id,),
            )
            assert cursor.fetchone()[0] == 0
        performance = PostgreSQLPerformanceRepository(database_url=DATABASE_URL)
        assert performance.summary(valid_account).realized_pnl_minor == valid_pick.stake_minor
        assert performance.summary(disputed_account).realized_pnl_minor == 0
        assert runtime.readiness_snapshot()[1]["result_conflicts"] == 1
    finally:
        runtime.clear_item_failure("results", disputed.fixture_id)
        _cleanup(valid_account, (disputed, valid))


def test_failed_quarantine_write_aborts_reconciliation(monkeypatch) -> None:
    assert DATABASE_URL is not None
    _migrate()
    disputed = _candidate()
    account = f"ledger-failure-{uuid4()}"
    pick = _registered(disputed, account)
    assert pick is not None
    runtime = PostgreSQLRuntimeRepository(database_url=DATABASE_URL)
    repository = PostgreSQLResultSettlementRepository(
        ResultSettlementPolicy(), database_url=DATABASE_URL
    )
    payload = _payload(disputed, _fixture_cutoff(disputed))
    payload["teams"]["home"]["id"] = 2
    payload["teams"]["away"]["id"] = 1
    at = _fixture_cutoff(disputed) + timedelta(hours=2)

    def failed_write(*_args, **_kwargs):
        raise psycopg.OperationalError("injected failure-ledger write error")

    monkeypatch.setattr(runtime, "record_item_failure", failed_write)

    def record_failure(fixture_id, error, failed_at):
        runtime.record_item_failure("results", fixture_id, error, failed_at=failed_at)

    reconcile = ReconcileFixtureResults(
        repository,
        Source({disputed.fixture_id: payload}),  # type: ignore[arg-type]
        clock=lambda: at,
        on_item_failure=record_failure,
    )
    try:
        with pytest.raises(psycopg.OperationalError, match="injected failure-ledger"):
            reconcile.execute()
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM fixture_result_observations WHERE fixture_id = %s",
                (disputed.fixture_id,),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT count(*) FROM production_item_failures "
                "WHERE worker_name = 'results' AND item_id = %s", (disputed.fixture_id,)
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT count(*) FROM pick_settlement_events WHERE pick_id = %s",
                (pick.pick_id,),
            )
            assert cursor.fetchone()[0] == 0
        assert runtime.readiness_snapshot()[1]["result_conflicts"] == 0
    finally:
        _cleanup(account, (disputed,))
