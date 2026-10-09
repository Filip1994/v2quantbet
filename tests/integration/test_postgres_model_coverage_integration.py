from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql

from h2h.domain.model_coverage import ModelCoverageStatus, ProductionTrainingPolicy
from h2h.odds.budget import (
    ApiBudgetExceededError,
    PostgreSQLApiBudget,
    provider_request_category,
)
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_model_coverage import PostgreSQLModelCoverageRepository


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MIGRATION_DIR = Path(__file__).parents[2] / "migrations"


@pytest.fixture
def isolated_database(tmp_path):
    assert DATABASE_URL is not None
    schema = f"model_coverage_{uuid4().hex}"
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connect():
        return psycopg.connect(DATABASE_URL, options=f"-c search_path={schema}")

    try:
        # This suite exercises the model-coverage schema. Later migrations
        # include operator-specific settlements that require production evidence
        # and cannot run against an empty temporary database.
        migration_subset = tmp_path / "model_coverage_migrations"
        migration_subset.mkdir()
        for migration in sorted(MIGRATION_DIR.glob("*.sql")):
            if migration.name[:3].isdigit() and int(migration.name[:3]) <= 10:
                shutil.copyfile(migration, migration_subset / migration.name)
        with connect() as connection:
            apply_migrations(connection, migration_subset)
        yield connect
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def insert_fixture(connect, *, fixture_id: int, league_id: int, season: int, now: datetime):
    canonical = f"api-football:{fixture_id}"
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO fixtures (fixture_id, provider, provider_fixture_id, league_id, "
            "season, provider_home_team_id, provider_away_team_id, created_at) VALUES "
            "(%s, 'api-football', %s, %s, %s, %s, %s, %s)",
            (canonical, str(fixture_id), league_id, season, fixture_id + 1, fixture_id + 2, now),
        )
        cursor.execute(
            "INSERT INTO fixture_observations (fixture_observation_id, fixture_id, home_team, "
            "away_team, competition_name, country, competition_type, kickoff_at, "
            "provider_status, source, observed_at) VALUES (%s, %s, 'Home', 'Away', "
            "'Premier League', 'England', 'League', %s, 'NS', 'test', %s)",
            (f"fixture-observation-v1:{fixture_id:064x}", canonical, now + timedelta(hours=2), now),
        )


def test_inventory_queue_is_scope_bounded_and_restart_safe(isolated_database) -> None:
    connect = isolated_database
    now = datetime(2026, 9, 23, 12, tzinfo=UTC)
    insert_fixture(connect, fixture_id=100, league_id=39, season=2026, now=now)
    insert_fixture(connect, fixture_id=200, league_id=40, season=2026, now=now)
    repository = PostgreSQLModelCoverageRepository(connect=connect)
    policy = ProductionTrainingPolicy()

    assert repository.refresh_inventory(policy, now=now) == 2
    counts = repository.coverage_counts()
    assert counts.total_eligible == counts.training_required == 2
    claimed = repository.claim_training_scopes(now=now, limit=1)
    assert len(claimed) == 1
    assert claimed[0].status is ModelCoverageStatus.TRAINING_PENDING
    assert repository.coverage_counts().training_pending == 1
    assert repository.recover_abandoned_claims(
        now=now + timedelta(seconds=91), lease_seconds=90
    ) == 1
    assert repository.coverage_counts().training_required == 2

    payload = {"errors": [], "results": 0, "paging": {"current": 1, "total": 1}, "response": []}
    start, end = policy.training_window(now)
    repository.save_acquisition(
        league_id=39,
        season=2025,
        start_at=start,
        end_at=end,
        payload=payload,
        accepted_match_count=0,
        acquired_at=now,
    )
    restarted = PostgreSQLModelCoverageRepository(connect=connect)
    assert restarted.load_acquisition(
        league_id=39,
        season=2025,
        start_at=start,
        end_at=end,
    ) == payload


def test_inventory_refresh_avoids_rewriting_unchanged_eligibility(isolated_database) -> None:
    connect = isolated_database
    now = datetime(2026, 9, 23, 12, tzinfo=UTC)
    insert_fixture(connect, fixture_id=100, league_id=39, season=2026, now=now)
    insert_fixture(connect, fixture_id=200, league_id=40, season=2026, now=now)
    repository = PostgreSQLModelCoverageRepository(connect=connect)
    policy = ProductionTrainingPolicy()
    assert repository.refresh_inventory(policy, now=now) == 2

    with connect() as connection:
        connection.execute("CREATE TABLE inventory_updates (league_id bigint, old_eligible boolean, "
                           "new_eligible boolean)")
        connection.execute("""
            CREATE FUNCTION count_inventory_update() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                INSERT INTO inventory_updates VALUES
                    (NEW.league_id, OLD.eligible, NEW.eligible);
                RETURN NEW;
            END $$
        """)
        connection.execute("""
            CREATE TRIGGER count_inventory_update AFTER UPDATE ON model_coverage_scopes
            FOR EACH ROW EXECUTE FUNCTION count_inventory_update()
        """)

    # An unchanged cycle still updates the contractual refreshed timestamp,
    # but no longer performs the former TRUE -> FALSE -> TRUE reset.
    assert repository.refresh_inventory(policy, now=now + timedelta(minutes=1)) == 2
    with connect() as connection:
        updates = connection.execute(
            "SELECT league_id, old_eligible, new_eligible FROM inventory_updates "
            "ORDER BY league_id"
        ).fetchall()
        assert len(updates) == 4  # one UPSERT and one status refresh per scope
        assert all(old and new for _, old, new in updates)
        connection.execute("DELETE FROM inventory_updates")
        connection.execute(
            "UPDATE fixture_observations SET kickoff_at = %s WHERE fixture_id = %s",
            (now - timedelta(hours=1), "api-football:200"),
        )

    assert repository.refresh_inventory(policy, now=now + timedelta(minutes=2)) == 1
    with connect() as connection:
        updates = connection.execute(
            "SELECT league_id, old_eligible, new_eligible FROM inventory_updates "
            "ORDER BY league_id, new_eligible"
        ).fetchall()
        assert updates.count((40, True, False)) == 1
        assert updates.count((39, True, True)) == 2
        scopes = connection.execute(
            "SELECT league_id, eligible FROM model_coverage_scopes ORDER BY league_id"
        ).fetchall()
        assert scopes == [(39, True), (40, False)]
        connection.execute("DELETE FROM inventory_updates")

    # A previously excluded scope remains excluded without another dead write.
    assert repository.refresh_inventory(policy, now=now + timedelta(minutes=3)) == 1
    with connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM inventory_updates WHERE league_id = 40"
        ).fetchone()[0] == 0


def test_persistent_training_budget_reserves_live_capacity(isolated_database) -> None:
    connect = isolated_database
    now = datetime(2026, 9, 23, 12, tzinfo=UTC)
    budget = PostgreSQLApiBudget(
        daily_limit=5,
        reserve=0,
        training_daily_limit=1,
        operational_reserve=2,
        connect=connect,
        clock=lambda: now,
    )

    with provider_request_category("model_training"):
        budget.acquire()
        with pytest.raises(ApiBudgetExceededError, match="training"):
            budget.acquire()
    with provider_request_category("discovery"):
        budget.acquire()
    with provider_request_category("opportunity_odds"):
        budget.acquire()

    restarted = PostgreSQLApiBudget(
        daily_limit=5,
        reserve=0,
        training_daily_limit=1,
        operational_reserve=2,
        connect=connect,
        clock=lambda: now,
    )
    assert restarted.usage_by_category() == {
        "discovery": 1,
        "model_training": 1,
        "opportunity_odds": 1,
        "results_monitoring": 0,
        "quantlab_context": 0,
    }
