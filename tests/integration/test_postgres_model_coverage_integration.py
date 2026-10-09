from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
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


def test_inventory_baseline_candidate_transition_replay(isolated_database, tmp_path) -> None:
    """Replay the old blanket reset and new selective reset on paired schemas."""
    assert DATABASE_URL is not None
    candidate_connect = isolated_database
    baseline_schema = f"coverage_baseline_{uuid4().hex}"
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(baseline_schema)))

    migration_subset = tmp_path / "baseline_migrations"
    migration_subset.mkdir()
    for migration in sorted(MIGRATION_DIR.glob("*.sql")):
        if migration.name[:3].isdigit() and int(migration.name[:3]) <= 10:
            shutil.copyfile(migration, migration_subset / migration.name)

    def raw_baseline_connect():
        return psycopg.connect(DATABASE_URL, options=f"-c search_path={baseline_schema}")

    class BaselineCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def __enter__(self):
            self.cursor.__enter__()
            return self

        def __exit__(self, *args):
            return self.cursor.__exit__(*args)

        def execute(self, query, params=None):
            if isinstance(query, str) and query.startswith(
                "UPDATE model_coverage_scopes c SET eligible = FALSE"
            ):
                # Exact SQL replaced by this PR. All other production code runs
                # unchanged in both replay branches.
                return self.cursor.execute("UPDATE model_coverage_scopes SET eligible = FALSE")
            return self.cursor.execute(query, params)

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    class BaselineConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def cursor(self):
            return BaselineCursor(self.connection.cursor())

    def baseline_connect():
        return BaselineConnection(raw_baseline_connect())

    def snapshot(connect):
        with connect() as connection:
            return connection.execute(
                "SELECT * "
                "FROM model_coverage_scopes ORDER BY league_id,season"
            ).fetchall()

    now = datetime(2026, 9, 23, 12, tzinfo=UTC)
    policy = ProductionTrainingPolicy()
    changed_policy = ProductionTrainingPolicy(min_matches=100)
    try:
        with raw_baseline_connect() as connection:
            apply_migrations(connection, migration_subset)
        candidate = PostgreSQLModelCoverageRepository(connect=candidate_connect)
        baseline = PostgreSQLModelCoverageRepository(connect=baseline_connect)

        def refresh(at, current_policy):
            assert baseline.refresh_inventory(current_policy, now=at) == candidate.refresh_inventory(
                current_policy, now=at
            )
            assert snapshot(raw_baseline_connect) == snapshot(candidate_connect)

        refresh(now, policy)  # empty universe
        for connect in (raw_baseline_connect, candidate_connect):
            insert_fixture(connect, fixture_id=100, league_id=39, season=2026, now=now)
            insert_fixture(connect, fixture_id=200, league_id=40, season=2026, now=now)
        refresh(now, policy)
        refresh(now + timedelta(minutes=1), policy)  # unchanged universe

        for connect in (raw_baseline_connect, candidate_connect):
            with connect() as connection:
                connection.execute(
                    "UPDATE fixture_observations SET kickoff_at=%s WHERE fixture_id=%s",
                    (now - timedelta(hours=1), "api-football:200"),
                )
        refresh(now + timedelta(minutes=2), policy)  # removed league

        for connect in (raw_baseline_connect, candidate_connect):
            with connect() as connection:
                connection.execute(
                    "UPDATE fixture_observations SET kickoff_at=%s WHERE fixture_id=%s",
                    (now + timedelta(days=2), "api-football:200"),
                )
        refresh(now + timedelta(minutes=3), policy)  # returned league
        refresh(now + timedelta(minutes=4), changed_policy)  # policy change

        baseline_claims = baseline.claim_training_scopes(now=now + timedelta(minutes=5), limit=1)
        candidate_claims = candidate.claim_training_scopes(now=now + timedelta(minutes=5), limit=1)
        assert baseline_claims == candidate_claims
        assert snapshot(raw_baseline_connect) == snapshot(candidate_connect)

        # Concurrent cron invocations with the same clock/policy must settle
        # to the same durable rows as the baseline.
        def concurrent_refresh(repository):
            with ThreadPoolExecutor(max_workers=2) as pool:
                return sorted(pool.map(
                    lambda _: repository.refresh_inventory(
                        changed_policy, now=now + timedelta(minutes=6)
                    ), range(2)
                ))

        assert concurrent_refresh(baseline) == concurrent_refresh(candidate)
        assert snapshot(raw_baseline_connect) == snapshot(candidate_connect)

        # Synthetic active pointer: the inventory refresh must promote the
        # same scope to ACTIVE and later STALE on both SQL paths.
        artifact = b"synthetic-model-coverage-replay"
        digest = sha256(artifact).hexdigest()
        model_id = f"dcm-json-v1:{digest}"
        for connect in (raw_baseline_connect, candidate_connect):
            with connect() as connection:
                connection.execute(
                    "UPDATE fixture_observations SET kickoff_at=%s",
                    (now + timedelta(days=30),),
                )
                connection.execute("""
                    INSERT INTO dixon_coles_model_versions (
                      model_version_id,provider,team_id_namespace,league_id,season,
                      training_start_at,training_end_at,reference_time,xi,ridge,
                      min_matches,accepted_match_count,fitted_match_count,
                      earliest_match_at,latest_match_at,dataset_sha256,
                      training_input_fingerprint,trained_at,artifact_schema_version,
                      training_dataset_schema_version,model_implementation_version,
                      trainer_code_version,python_version,numpy_version,scipy_version,
                      artifact_sha256,artifact_bytes)
                    VALUES (%s,'api-football','api-football',39,2026,
                      %s,%s,%s,0.0018,0.01,80,80,80,%s,%s,%s,%s,%s,
                      1,1,'synthetic','synthetic','3.11','2.3','1.17',%s,%s)
                """, (model_id, now - timedelta(days=100), now - timedelta(days=1),
                      now, now - timedelta(days=90), now - timedelta(days=2),
                      "a" * 64, "b" * 64, now, digest, artifact))
                connection.execute("""
                    INSERT INTO dixon_coles_active_models (
                      provider,team_id_namespace,league_id,season,
                      model_version_id,activated_at,generation)
                    VALUES ('api-football','api-football',39,2026,%s,%s,1)
                """, (model_id, now + timedelta(minutes=6)))
        refresh(now + timedelta(minutes=7), changed_policy)
        refresh(now + timedelta(days=15), changed_policy)  # stale clock boundary
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(baseline_schema))
            )


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
