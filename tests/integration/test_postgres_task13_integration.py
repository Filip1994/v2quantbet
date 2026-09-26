from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql

from h2h.config import load_registration_policy_config
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_pick_registration import PostgreSQLPickRegistrationRepository
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository
from h2h.persistence.pick_registration import BankrollBootstrapConflictError
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy
from tests.test_config import registration_environment


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MIGRATION_DIR = Path(__file__).parents[2] / "migrations"


@pytest.fixture
def isolated_database():
    assert DATABASE_URL is not None
    schema = f"task13_{uuid4().hex}"
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connect():
        return psycopg.connect(DATABASE_URL, options=f"-c search_path={schema}")

    try:
        yield schema, connect
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _activate_model_scope(cursor, *, league_id: int, season: int, now: datetime) -> None:
    cursor.execute(
        "INSERT INTO model_coverage_scopes (provider, team_id_namespace, league_id, season, "
        "status, first_required_at, updated_at, policy_fingerprint, active_model_version_id, "
        "active_generation) VALUES ('api-football', 'api-football', %s, %s, 'ACTIVE', "
        "%s, %s, %s, %s, 1)",
        (league_id, season, now, now, "0" * 64, f"test-model:{league_id}:{season}"),
    )


def test_fresh_schema_runtime_leadership_and_bankroll(isolated_database) -> None:
    _schema, connect = isolated_database
    with connect() as connection:
        applied = apply_migrations(connection, MIGRATION_DIR)
    expected = tuple(path.name for path in sorted(MIGRATION_DIR.glob("*.sql")))
    assert applied == expected
    assert expected[-1] == "025_quantlab_market_collector_cardlab_v1.sql"

    runtime = PostgreSQLRuntimeRepository(connect=connect)
    assert runtime.check_database()
    assert runtime.verify_schema(expected) == expected

    now = datetime.now(UTC)
    runtime.worker_started("opportunity", "instance-a", at=now)
    runtime.worker_succeeded(
        "opportunity", "instance-a", at=now, next_due_at=now + timedelta(minutes=1)
    )
    status = runtime.worker_statuses()[0]
    assert status.worker_name == "opportunity"
    assert status.cycle_count == status.success_count == 1

    first = runtime.open_leader_lock()
    second = runtime.open_leader_lock()
    try:
        assert first.try_acquire()
        assert not second.try_acquire()
        first.close()
        assert second.try_acquire()
    finally:
        if first.acquired:
            first.close()
        second.close()

    policy = load_registration_policy_config(registration_environment())
    registration = PostgreSQLPickRegistrationRepository(connect=connect)
    registration.bootstrap_bankroll(policy, occurred_at=now)
    runtime.verify_bankroll(
        policy.bankroll_account_id, policy.currency, policy.initial_bankroll_minor
    )
    with pytest.raises(RuntimeError, match="conflict"):
        runtime.verify_bankroll(
            policy.bankroll_account_id, policy.currency, policy.initial_bankroll_minor + 1
        )
    with pytest.raises(BankrollBootstrapConflictError):
        registration.bootstrap_bankroll(replace(policy, currency="EUR"), occurred_at=now)


def test_durable_opportunity_query_uses_phase_i_policy_not_manual_scope(isolated_database) -> None:
    _schema, connect = isolated_database
    with connect() as connection:
        apply_migrations(connection, MIGRATION_DIR)
    now = datetime.now(UTC)
    fixture_id = "api-football:987654321"
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO fixtures (fixture_id, provider, provider_fixture_id, league_id, "
            "season, provider_home_team_id, provider_away_team_id, created_at) "
            "VALUES (%s, 'api-football', '987654321', 140, 2026, 1, 2, %s)",
            (fixture_id, now),
        )
        cursor.execute(
            "INSERT INTO fixture_observations (fixture_observation_id, fixture_id, home_team, "
            "away_team, competition_name, country, competition_type, kickoff_at, "
            "provider_status, source, observed_at) VALUES (%s, %s, 'Home', 'Away', "
            "'La Liga', 'Spain', 'League', %s, 'NS', 'api-football', %s)",
            ("fixture-observation-v1:" + "a" * 64, fixture_id, now + timedelta(hours=2), now),
        )
        _activate_model_scope(cursor, league_id=140, season=2026, now=now)

    runtime = PostgreSQLRuntimeRepository(connect=connect)
    due = runtime.due_opportunity_fixtures(
        bookmaker_id=8,
        allowed_statuses=("NS",),
        now=now,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=StaleQuoteRetryPolicy(
            timedelta(minutes=2), timedelta(minutes=15), 5, timedelta(hours=1)
        ),
    )
    assert tuple(item.fixture_id for item in due) == (fixture_id,)
    assert due[0].league_id == 140


def test_stale_complete_market_retry_is_exact_and_restart_safe(isolated_database) -> None:
    _schema, connect = isolated_database
    with connect() as connection:
        apply_migrations(connection, MIGRATION_DIR)
    now = datetime.now(UTC)
    old = now - timedelta(minutes=30)
    fixture_id = "api-football:1549793"
    policy = StaleQuoteRetryPolicy(
        timedelta(minutes=2), timedelta(minutes=8), 5, timedelta(minutes=30)
    )
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO fixtures (fixture_id, provider, provider_fixture_id, league_id, "
            "season, provider_home_team_id, provider_away_team_id, created_at) "
            "VALUES (%s, 'api-football', '1549793', 239, 2026, 1, 2, %s)",
            (fixture_id, now),
        )
        cursor.execute(
            "INSERT INTO fixture_observations (fixture_observation_id, fixture_id, home_team, "
            "away_team, competition_name, country, competition_type, kickoff_at, "
            "provider_status, source, observed_at) VALUES (%s, %s, 'América de Cali', "
            "'Águilas Doradas', 'Primera A', 'Colombia', 'League', %s, 'NS', "
            "'api-football', %s)",
            ("fixture-observation-v1:" + "b" * 64, fixture_id, now + timedelta(hours=4), now),
        )
        _activate_model_scope(cursor, league_id=239, season=2026, now=now)
        for selection in ("YES", "NO"):
            cursor.execute(
                "INSERT INTO quote_series (series_id, fixture_id, bookmaker_id, market, "
                "selection, created_at) VALUES (%s, %s, 8, 'BTTS', %s, %s)",
                (f"series-{selection.lower()}", fixture_id, selection, now),
            )
        # Different observation timestamps must not form a complete market.
        cursor.execute(
            "INSERT INTO quote_snapshots VALUES "
            "('snapshot-yes-new', 'series-yes', 1.80, %s, %s, 'api-football'), "
            "('snapshot-no-old', 'series-no', 1.73, %s, %s, 'api-football')",
            (now, now, old, now),
        )

    runtime = PostgreSQLRuntimeRepository(connect=connect)
    assert runtime.latest_complete_market_states(fixture_id, 8) == ()

    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO quote_snapshots VALUES "
            "('snapshot-yes-old', 'series-yes', 2.10, %s, %s, 'api-football')",
            (old, now),
        )

    markets = runtime.latest_complete_market_states(fixture_id, 8)
    assert len(markets) == 1
    assert markets[0].observed_at == old
    due = runtime.select_opportunity_fixtures(
        bookmaker_id=8,
        allowed_statuses=("NS",),
        now=now,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=policy,
    )
    assert due.due_fixtures[0].stale_retry is True

    state = runtime.record_quote_refresh_state(
        fixture_id,
        8,
        freshness_state="STALE",
        attempted_at=now,
        latest_observed_at=old,
        latest_captured_at=now,
        stale_retry_policy=policy,
    )
    assert state.next_retry_at == now + timedelta(minutes=2)

    # A new repository instance proves the retry boundary is durable across restart.
    restarted = PostgreSQLRuntimeRepository(connect=connect)
    waiting = restarted.select_opportunity_fixtures(
        bookmaker_id=8,
        allowed_statuses=("NS",),
        now=now + timedelta(minutes=1),
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=policy,
    )
    retry = restarted.select_opportunity_fixtures(
        bookmaker_id=8,
        allowed_statuses=("NS",),
        now=now + timedelta(minutes=2),
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=policy,
    )
    assert waiting.due_fixtures == ()
    assert retry.due_fixtures[0].stale_retry is True
