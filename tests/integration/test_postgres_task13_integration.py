from __future__ import annotations

import json
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
from h2h.quantlab.goal_lab.picks import (
    settle_goal_pick,
    stable_goal_result_evidence,
)
from h2h.quantlab.repository import PostgreSQLQuantLabRepository
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
    assert expected[-1] == "054_quantlab_goallab_positive_ev_policy.sql"

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


def test_goallab_dashboard_queries_work_on_fresh_schema(isolated_database) -> None:
    _schema, connect = isolated_database
    with connect() as connection:
        apply_migrations(connection, MIGRATION_DIR)

    now = datetime.now(UTC)
    fixture_id = "api-football:9900001"
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO quantlab_fixtures "
            "(fixture_id, provider_fixture_id, first_seen_at) VALUES (%s, %s, %s)",
            (fixture_id, 9_900_001, now),
        )
        cursor.execute(
            "INSERT INTO quantlab_fixture_observations ("
            "fixture_observation_id, fixture_id, provider_fixture_id, league_id, season, "
            "home_team_id, away_team_id, home_team, away_team, competition_name, country, "
            "competition_type, kickoff_at, provider_status, captured_at, raw_payload"
            ") VALUES (%s, %s, %s, 39, 2026, 1, 2, 'Home', 'Away', "
            "'Premier League', 'England', 'League', %s, 'NS', %s, '{}'::jsonb)",
            (
                "quantlab-fixture-v1:" + "a" * 64,
                fixture_id,
                9_900_001,
                now + timedelta(hours=4),
                now,
            ),
        )
        cursor.execute(
            "INSERT INTO quantlab_goal_decisions ("
            "decision_id, fixture_id, decision_at, policy_version, model_name, model_version, "
            "decision, reason, evidence_fingerprint, details"
            ") VALUES (%s, %s, %s, 'GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V2', "
            "'DC+ Pro Structural', %s, 'PASS', 'EDGE_BELOW_MINIMUM', %s, '{}'::jsonb)",
            (
                "quantlab-goal-decision-v1:" + "b" * 64,
                fixture_id,
                now,
                "DC_PLUS_PRO_STRUCTURAL_V1:" + "c" * 64,
                "d" * 64,
            ),
        )

    repository = PostgreSQLQuantLabRepository(connect=connect)
    pipeline = repository.list_goal_fixture_status(now=now)
    decisions = repository.list_all_goal_decisions()

    assert len(pipeline) == 1
    assert pipeline[0]["fixture_id"] == fixture_id
    assert pipeline[0]["reason"] == "EDGE_BELOW_MINIMUM"
    assert len(decisions) == 1
    assert decisions[0]["fixture_id"] == fixture_id
    assert decisions[0]["competition_name"] == "Premier League"




def test_goallab_dashboard_prefers_canonical_decision_over_better_price_pass(
    isolated_database,
) -> None:
    _schema, connect = isolated_database
    with connect() as connection:
        apply_migrations(connection, MIGRATION_DIR)

    now = datetime.now(UTC)
    fixture_id = "api-football:9900002"
    model_version = "DC_PLUS_PRO_STRUCTURAL_V3:" + "e" * 64
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO quantlab_fixtures "
            "(fixture_id, provider_fixture_id, first_seen_at) VALUES (%s, %s, %s)",
            (fixture_id, 9_900_002, now),
        )
        cursor.execute(
            "INSERT INTO quantlab_fixture_observations ("
            "fixture_observation_id, fixture_id, provider_fixture_id, league_id, season, "
            "home_team_id, away_team_id, home_team, away_team, competition_name, country, "
            "competition_type, kickoff_at, provider_status, captured_at, raw_payload"
            ") VALUES (%s, %s, %s, 39, 2026, 1, 2, 'Home', 'Away', "
            "'Premier League', 'England', 'League', %s, 'NS', %s, '{}'::jsonb)",
            (
                "quantlab-fixture-v1:" + "f" * 64,
                fixture_id,
                9_900_002,
                now + timedelta(hours=4),
                now,
            ),
        )
        cursor.execute(
            "INSERT INTO quantlab_goal_decisions ("
            "decision_id, fixture_id, decision_at, policy_version, model_name, model_version, "
            "bookmaker_id, bookmaker_name, provider_bet_id, provider_bet_name, market_key, "
            "selection, line, quote_observed_at, odds, companion_odds, market_probability, "
            "model_probability, edge, expected_value, decision, reason, evidence_fingerprint, "
            "details"
            ") VALUES "
            "(%s, %s, %s, 'GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V5', "
            "'DC+ Pro Structural', %s, 8, 'Book A', 5, 'Goals Over/Under', 'OU_25', "
            "'OVER', 2.5, %s, 1.80, 2.00, 0.52, 0.57, 0.05, 0.026, "
            "'PASS', 'BETTER_PRICE_AVAILABLE', %s, '{}'::jsonb), "
            "(%s, %s, %s, 'GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V5', "
            "'DC+ Pro Structural', %s, 9, 'Book B', 5, 'Goals Over/Under', 'OU_25', "
            "'OVER', 2.5, %s, 1.90, 1.90, 0.50, 0.57, 0.07, 0.083, "
            "'PASS', 'CANONICAL_FIXTURE_SIGNAL_ONLY', %s, '{}'::jsonb)",
            (
                "quantlab-goal-decision-v1:" + "1" * 64,
                fixture_id,
                now,
                model_version,
                now,
                "2" * 64,
                "quantlab-goal-decision-v1:" + "3" * 64,
                fixture_id,
                now,
                model_version,
                now,
                "4" * 64,
            ),
        )

    repository = PostgreSQLQuantLabRepository(connect=connect)
    pipeline = repository.list_goal_fixture_status(now=now)

    assert len(pipeline) == 1
    assert pipeline[0]["fixture_id"] == fixture_id
    assert pipeline[0]["reason"] == "CANONICAL_FIXTURE_SIGNAL_ONLY"
    assert pipeline[0]["bookmaker_name"] == "Book B"
    assert float(pipeline[0]["odds"]) == 1.90
    assert float(pipeline[0]["expected_value"]) == pytest.approx(0.083)


def test_goallab_pick_result_refresh_to_settlement_e2e(isolated_database) -> None:
    _schema, connect = isolated_database
    with connect() as connection:
        apply_migrations(connection, MIGRATION_DIR)

    now = datetime.now(UTC).replace(microsecond=0)
    kickoff = now - timedelta(hours=3)
    decision_at = kickoff - timedelta(hours=2)
    quote_at = decision_at - timedelta(minutes=5)
    first_terminal = kickoff + timedelta(hours=2)
    second_terminal = first_terminal + timedelta(minutes=15)
    fixture_id = "api-football:9900101"
    provider_fixture_id = 9_900_101
    model_version = "DC_PLUS_PRO_STRUCTURAL_V1:" + "1" * 64
    feature_snapshot_id = "quantlab-goal-features-v1:" + "2" * 64
    selected_observation_id = "quantlab-market-v1:" + "3" * 64
    companion_observation_id = "quantlab-market-v1:" + "4" * 64
    decision_id = "quantlab-goal-decision-v1:" + "5" * 64
    goal_pick_id = "quantlab-goal-pick-v1:" + "6" * 64

    def provider_payload(status: str, home: int | None, away: int | None) -> dict:
        return {
            "fixture": {
                "id": provider_fixture_id,
                "date": kickoff.isoformat(),
                "status": {"short": status},
            },
            "teams": {
                "home": {"id": 101, "name": "Home"},
                "away": {"id": 202, "name": "Away"},
            },
            "goals": {"home": home, "away": away},
            "score": {
                "fulltime": {"home": home, "away": away},
                "extratime": {"home": None, "away": None},
                "penalty": {"home": None, "away": None},
            },
        }

    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO quantlab_fixtures "
            "(fixture_id, provider_fixture_id, first_seen_at) VALUES (%s, %s, %s)",
            (fixture_id, provider_fixture_id, decision_at - timedelta(hours=1)),
        )
        cursor.execute(
            "INSERT INTO quantlab_fixture_observations ("
            "fixture_observation_id, fixture_id, provider_fixture_id, league_id, season, "
            "home_team_id, away_team_id, home_team, away_team, competition_name, country, "
            "competition_type, kickoff_at, provider_status, captured_at, raw_payload"
            ") VALUES (%s, %s, %s, 39, 2026, 101, 202, 'Home', 'Away', "
            "'Premier League', 'England', 'League', %s, 'NS', %s, %s::jsonb)",
            (
                "quantlab-fixture-v1:" + "7" * 64,
                fixture_id,
                provider_fixture_id,
                kickoff,
                decision_at - timedelta(hours=1),
                json.dumps(provider_payload("NS", None, None)),
            ),
        )
        cursor.execute(
            "INSERT INTO quantlab_goal_model_versions ("
            "model_version, trained_at, training_cutoff, feature_version, "
            "training_sample_size, history_match_count, team_count, league_count, "
            "ridge_team, ridge_feature, rho, intercept, home_advantage, parameters, "
            "feature_means, feature_scales, training_payload"
            ") VALUES (%s, %s, %s, 'GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1', "
            "100, 120, 20, 2, 1, 1, -0.04, 0.1, 0.2, '{}'::jsonb, '{}'::jsonb, "
            "'{}'::jsonb, '{}'::jsonb)",
            (model_version, decision_at - timedelta(days=1), decision_at - timedelta(days=1)),
        )
        cursor.execute(
            "INSERT INTO quantlab_goal_feature_snapshots ("
            "feature_snapshot_id, fixture_id, decision_at, model_version, "
            "expected_home_goals, expected_away_goals, home_history_size, "
            "away_history_size, feature_payload"
            ") VALUES (%s, %s, %s, %s, 1.80, 1.10, 10, 10, '{}'::jsonb)",
            (feature_snapshot_id, fixture_id, decision_at, model_version),
        )
        for observation_id, raw_selection, odds in (
            (selected_observation_id, "Over 2.5", 1.95),
            (companion_observation_id, "Under 2.5", 1.85),
        ):
            cursor.execute(
                "INSERT INTO quantlab_market_observations ("
                "market_observation_id, fixture_id, provider_fixture_id, bookmaker_id, "
                "bookmaker_name, provider_bet_id, provider_bet_name, raw_selection, "
                "parsed_line, odds, captured_at, lab_owner, classifier_version, raw_payload"
                ") VALUES (%s, %s, %s, 8, 'Bet365', 5, 'Goals Over/Under', %s, "
                "2.5, %s, %s, 'GOAL', 'MARKET_CLASSIFIER_V1', '{}'::jsonb)",
                (
                    observation_id,
                    fixture_id,
                    provider_fixture_id,
                    raw_selection,
                    odds,
                    quote_at,
                ),
            )
        cursor.execute(
            "INSERT INTO quantlab_goal_decisions ("
            "decision_id, fixture_id, decision_at, policy_version, model_name, model_version, "
            "bookmaker_id, bookmaker_name, provider_bet_id, provider_bet_name, market_key, "
            "selection, line, selected_observation_id, companion_observation_id, "
            "quote_observed_at, odds, companion_odds, market_probability, model_probability, "
            "edge, expected_value, decision, reason, evidence_fingerprint, details"
            ") VALUES (%s, %s, %s, 'GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V2', "
            "'DC+ Pro Structural', %s, 8, 'Bet365', 5, 'Goals Over/Under', 'OU_25', "
            "'OVER', 2.5, %s, %s, %s, 1.95, 1.85, 0.52, 0.60, 0.08, 0.17, "
            "'PICK', 'CANONICAL_FIXTURE_PICK', %s, '{}'::jsonb)",
            (
                decision_id,
                fixture_id,
                decision_at,
                model_version,
                selected_observation_id,
                companion_observation_id,
                quote_at,
                "8" * 64,
            ),
        )
        cursor.execute(
            "INSERT INTO quantlab_goal_picks ("
            "goal_pick_id, fixture_id, source_decision_id, feature_snapshot_id, "
            "pick_policy_version, model_name, model_version, bookmaker_id, bookmaker_name, "
            "provider_bet_id, provider_bet_name, market_key, selection, line, "
            "selected_observation_id, companion_observation_id, quote_observed_at, "
            "decision_at, kickoff_at, odds, companion_odds, market_probability, "
            "model_probability, edge, expected_value, expected_home_goals, "
            "expected_away_goals, rho, stake_minor, qualifying_candidate_count, "
            "selection_rank_payload"
            ") VALUES (%s, %s, %s, %s, 'GOALLAB_DC_PLUS_PICK_POLICY_V1', "
            "'DC+ Pro Structural', %s, 8, 'Bet365', 5, 'Goals Over/Under', 'OU_25', "
            "'OVER', 2.5, %s, %s, %s, %s, %s, 1.95, 1.85, 0.52, 0.60, 0.08, 0.17, "
            "1.80, 1.10, -0.04, 10000, 2, '{}'::jsonb)",
            (
                goal_pick_id,
                fixture_id,
                decision_id,
                feature_snapshot_id,
                model_version,
                selected_observation_id,
                companion_observation_id,
                quote_at,
                decision_at,
                kickoff,
            ),
        )

    repository = PostgreSQLQuantLabRepository(connect=connect)

    refresh_due = repository.goal_pick_result_refresh_candidates(
        now=kickoff + timedelta(hours=2),
    )
    assert tuple(row["fixture_id"] for row in refresh_due) == (fixture_id,)

    with connect() as connection, connection.cursor() as cursor:
        for suffix, captured_at in (("9", first_terminal), ("a", second_terminal)):
            cursor.execute(
                "INSERT INTO quantlab_fixture_observations ("
                "fixture_observation_id, fixture_id, provider_fixture_id, league_id, season, "
                "home_team_id, away_team_id, home_team, away_team, competition_name, country, "
                "competition_type, kickoff_at, provider_status, captured_at, raw_payload"
                ") VALUES (%s, %s, %s, 39, 2026, 101, 202, 'Home', 'Away', "
                "'Premier League', 'England', 'League', %s, 'FT', %s, %s::jsonb)",
                (
                    "quantlab-fixture-v1:" + suffix * 64,
                    fixture_id,
                    provider_fixture_id,
                    kickoff,
                    captured_at,
                    json.dumps(provider_payload("FT", 2, 1)),
                ),
            )

    candidates = repository.goal_pick_settlement_candidates(limit=10)
    assert len(candidates) == 1
    evidence = stable_goal_result_evidence(candidates[0])
    assert evidence is not None
    settlement_row = dict(candidates[0])
    settlement_row.update(evidence)
    settlement = settle_goal_pick(
        settlement_row,
        settled_at=second_terminal + timedelta(minutes=1),
    )
    assert settlement is not None
    assert settlement.outcome == "WIN"
    assert settlement.pnl_minor == 9_500
    assert repository.save_goal_pick_settlement(settlement) is True

    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT outcome, pnl_minor, result_classification, regulation_home_goals, "
            "regulation_away_goals, result_detail ->> 'result_confirmation_count' "
            "FROM quantlab_goal_pick_settlements WHERE goal_pick_id = %s",
            (goal_pick_id,),
        )
        stored = cursor.fetchone()

    assert stored == ("WIN", 9_500, "PLAYED_SETTLEABLE", 2, 1, "2")
    assert repository.goal_pick_settlement_candidates(limit=10) == ()
    assert repository.goal_pick_result_refresh_candidates(
        now=second_terminal + timedelta(hours=1),
    ) == ()
