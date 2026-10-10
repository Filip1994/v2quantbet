"""Real PostgreSQL check for disputed result rollback and durable quarantine."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from h2h.domain.fixture_result import ApiFootballSettlementResultNormalizer
from h2h.domain.settlement import ResultSettlementPolicy
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository
from h2h.persistence.result_settlement import ResultPersistenceConflictError


psycopg = pytest.importorskip("psycopg")
DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="isolated PostgreSQL required")
NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)


def test_conflict_rolls_back_and_quarantine_excludes_only_disputed_fixture() -> None:
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        apply_migrations(connection, Path(__file__).parents[2] / "migrations")
    disputed_number = int(uuid4().int % 900_000_000) + 100_000_000
    valid_number = disputed_number + 1
    disputed = f"api-football:{disputed_number}"
    valid = f"api-football:{valid_number}"
    repository = PostgreSQLResultSettlementRepository(
        ResultSettlementPolicy(), database_url=DATABASE_URL
    )
    runtime = PostgreSQLRuntimeRepository(database_url=DATABASE_URL)
    try:
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            for fixture_id, number in ((disputed, disputed_number), (valid, valid_number)):
                cursor.execute(
                    "INSERT INTO fixtures (fixture_id, provider, provider_fixture_id, league_id, "
                    "season, provider_home_team_id, provider_away_team_id, created_at) "
                    "VALUES (%s, 'api-football', %s, 39, 2026, 1, 2, %s)",
                    (fixture_id, str(number), NOW),
                )
                cursor.execute(
                    "INSERT INTO fixture_result_acquisition_states "
                    "(fixture_id, phase, next_check_at, updated_at, version) "
                    "VALUES (%s, 'WAITING', %s, %s, 1)",
                    (fixture_id, NOW, NOW),
                )
        payload = {
            "fixture": {"id": disputed_number, "date": NOW.isoformat(),
                        "status": {"short": "FT", "long": "Match Finished"}},
            "league": {"id": 39, "season": 2026},
            "teams": {"home": {"id": 3}, "away": {"id": 2}},
            "goals": {"home": 2, "away": 1},
            "score": {"halftime": {"home": 1, "away": 0},
                      "fulltime": {"home": 2, "away": 1},
                      "extratime": {"home": None, "away": None},
                      "penalty": {"home": None, "away": None}},
        }
        result = ApiFootballSettlementResultNormalizer().normalize(
            payload, fixture_id=disputed, acquired_at=NOW
        )
        with pytest.raises(ResultPersistenceConflictError):
            repository.persist_result(result, checked_at=NOW)
        runtime.record_item_failure(
            "results", disputed, ResultPersistenceConflictError("fixture identity conflict"),
            failed_at=NOW,
        )
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM fixture_result_observations WHERE fixture_id = %s",
                (disputed,),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "SELECT last_error_class FROM production_item_failures "
                "WHERE worker_name = 'results' AND item_id = %s", (disputed,)
            )
            assert cursor.fetchone()[0] == "ResultPersistenceConflictError"
        assert repository.claim_due(claimed_at=NOW, limit=2) == (valid,)
        assert not repository.has_due_results(as_of=NOW)
        assert runtime.operational_counts()["result_conflicts"] == 1
        assert runtime.readiness_snapshot()[1]["result_conflicts"] == 1
        runtime.clear_item_failure("results", disputed)
        assert runtime.operational_counts()["result_conflicts"] == 0
        assert repository.claim_due(claimed_at=NOW, limit=2) == (disputed,)
    finally:
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM production_item_failures WHERE worker_name = 'results' "
                "AND item_id IN (%s, %s)", (disputed, valid)
            )
            cursor.execute(
                "DELETE FROM fixture_result_acquisition_states WHERE fixture_id IN (%s, %s)",
                (disputed, valid),
            )
            cursor.execute(
                "DELETE FROM fixtures WHERE fixture_id IN (%s, %s)", (disputed, valid)
            )
