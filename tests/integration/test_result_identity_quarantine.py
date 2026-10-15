"""A provider identity change must not rewrite PLAYED settlement or ledger facts."""

from datetime import timedelta
import os
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.fixture_result import ApiFootballSettlementResultNormalizer
from h2h.domain.settlement import ResultSettlementPolicy
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository
from h2h.persistence.result_settlement import FixtureResultIdentityConflictError
from tests.integration.test_postgres_task10_integration import _candidate, _cleanup
from tests.integration.test_postgres_task11_integration import _fixture_cutoff
from tests.integration.test_postgres_task12_integration import _payload, _registered, _confirm


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="test PostgreSQL is required")


@pytest.mark.parametrize("financial_state", ["none", "open", "settled"])
def test_identity_conflict_quarantines_without_changing_audit_or_money(financial_state):
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        apply_migrations(connection, Path(__file__).parents[2] / "migrations")
    candidate = _candidate()
    account = f"quarantine-{uuid4()}"
    repository = PostgreSQLResultSettlementRepository(
        ResultSettlementPolicy(), database_url=DATABASE_URL
    )
    kickoff = _fixture_cutoff(candidate)
    checked_at = kickoff + timedelta(hours=3)
    pick = None
    try:
        if financial_state != "none":
            pick = _registered(candidate, account)
        repository.reconcile(reconciled_at=checked_at)
        if financial_state == "none":
            # A result-only tracked fixture has no pick or research dependency.
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    "INSERT INTO fixture_result_acquisition_states "
                    "(fixture_id, phase, next_check_at, updated_at, version) "
                    "VALUES (%s, 'WAITING', %s, %s, 1)",
                    (candidate.fixture_id, checked_at, checked_at),
                )
        if financial_state == "settled":
            assert pick is not None
            original, settled_at = _confirm(repository, candidate, kickoff)
            repository.settle_pick(
                pick.pick_id, original.result_observation_id, settled_at=settled_at
            )
        with psycopg.connect(DATABASE_URL) as connection:
            before = connection.execute(
                "SELECT (SELECT COUNT(*) FROM fixture_result_observations WHERE fixture_id = %s), "
                "(SELECT COUNT(*) FROM pick_settlement_events WHERE fixture_id = %s), "
                "(SELECT COUNT(*) FROM bankroll_ledger_entries WHERE pick_id IN "
                "(SELECT pick_id FROM registered_picks WHERE fixture_id = %s)), "
                "(SELECT COALESCE(SUM(amount_minor), 0) FROM bankroll_ledger_entries "
                "WHERE pick_id IN (SELECT pick_id FROM registered_picks WHERE fixture_id = %s))",
                (candidate.fixture_id,) * 4,
            ).fetchone()
        payload = _payload(candidate, kickoff, score=(1, 0))
        payload["teams"] = {"home": {"id": 2}, "away": {"id": 1}}
        conflict = ApiFootballSettlementResultNormalizer().normalize(
            payload, fixture_id=candidate.fixture_id, acquired_at=checked_at
        )
        with pytest.raises(FixtureResultIdentityConflictError):
            repository.persist_result(conflict, checked_at=checked_at)
        first = repository.quarantine_identity_conflict(
            conflict, quarantined_at=checked_at
        )
        second = repository.quarantine_identity_conflict(
            conflict, quarantined_at=checked_at + timedelta(minutes=1)
        )
        assert first.newly_quarantined and not second.newly_quarantined
        assert first.financial_dependency == {
            "none": "NONE", "open": "OPEN_PLAYED", "settled": "SETTLED_PLAYED"
        }[financial_state]
        assert first.open_played_picks == int(financial_state == "open")
        assert first.settled_played_picks == int(financial_state == "settled")
        assert candidate.fixture_id not in repository.claim_due(
            claimed_at=checked_at + timedelta(hours=1)
        )
        assert candidate.fixture_id not in repository.reconcile(
            reconciled_at=checked_at + timedelta(days=1)
        )
        with psycopg.connect(DATABASE_URL) as connection:
            state = connection.execute(
                "SELECT phase, quarantine_reason, version FROM "
                "fixture_result_acquisition_states WHERE fixture_id = %s",
                (candidate.fixture_id,),
            ).fetchone()
            after = connection.execute(
                "SELECT (SELECT COUNT(*) FROM fixture_result_observations WHERE fixture_id = %s), "
                "(SELECT COUNT(*) FROM pick_settlement_events WHERE fixture_id = %s), "
                "(SELECT COUNT(*) FROM bankroll_ledger_entries WHERE pick_id IN "
                "(SELECT pick_id FROM registered_picks WHERE fixture_id = %s)), "
                "(SELECT COALESCE(SUM(amount_minor), 0) FROM bankroll_ledger_entries "
                "WHERE pick_id IN (SELECT pick_id FROM registered_picks WHERE fixture_id = %s))",
                (candidate.fixture_id,) * 4,
            ).fetchone()
        assert state[0] == "QUARANTINED"
        assert state[1]["code"] == "DURABLE_FIXTURE_IDENTITY_MISMATCH"
        assert state[1]["expected"]["home_team_id"] == 1
        assert state[1]["observed"]["home_team_id"] == 2
        assert state[2] > 1
        assert after == before
    finally:
        _cleanup(account, (candidate,))


def test_replayed_result_and_changed_score_keep_same_fixture_active():
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        apply_migrations(connection, Path(__file__).parents[2] / "migrations")
    candidate = _candidate()
    repository = PostgreSQLResultSettlementRepository(
        ResultSettlementPolicy(), database_url=DATABASE_URL
    )
    kickoff = _fixture_cutoff(candidate)
    checked_at = kickoff + timedelta(hours=3)
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO fixture_result_acquisition_states "
                "(fixture_id, phase, next_check_at, updated_at, version) "
                "VALUES (%s, 'WAITING', %s, %s, 1)",
                (candidate.fixture_id, checked_at, checked_at),
            )
        normalizer = ApiFootballSettlementResultNormalizer()
        original = normalizer.normalize(
            _payload(candidate, kickoff, score=(2, 1)),
            fixture_id=candidate.fixture_id, acquired_at=checked_at,
        )
        repository.persist_result(original, checked_at=checked_at)
        repository.persist_result(original, checked_at=checked_at)
        changed = normalizer.normalize(
            _payload(candidate, kickoff, score=(1, 0)),
            fixture_id=candidate.fixture_id,
            acquired_at=checked_at + timedelta(minutes=20),
        )
        repository.persist_result(changed, checked_at=checked_at + timedelta(minutes=20))
        with psycopg.connect(DATABASE_URL) as connection:
            state = connection.execute(
                "SELECT phase, quarantine_reason FROM fixture_result_acquisition_states "
                "WHERE fixture_id = %s", (candidate.fixture_id,),
            ).fetchone()
            observations = connection.execute(
                "SELECT COUNT(*) FROM fixture_result_observations WHERE fixture_id = %s",
                (candidate.fixture_id,),
            ).fetchone()[0]
        assert state[0] == "STABILIZING"
        assert state[1] is None
        assert observations == 2
    finally:
        _cleanup("no-account", (candidate,))
