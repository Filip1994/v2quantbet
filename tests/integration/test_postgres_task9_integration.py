from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.fixture import Fixture
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.prediction_record import PersistedFixturePrediction
from h2h.persistence.fixtures import FixturePersistenceConflictError
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_fixtures import PostgreSQLFixtureRepository
from h2h.persistence.postgres_model_lifecycle import PostgreSQLDixonColesModelVersionRepository
from h2h.persistence.postgres_predictions import PostgreSQLFixturePredictionRepository
from h2h.persistence.postgres_quote_history import PostgreSQLQuoteHistoryRepository
from h2h.persistence.postgres_value_evaluations import PostgreSQLValueEvaluationRepository
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.value_evaluation import EvaluatePersistedPredictionQuote
from tests.quant.test_dixon_coles_artifact import TRAINED_AT, trusted_artifact


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MIGRATION_DIR = Path(__file__).parents[2] / "migrations"


def test_task9_full_postgresql_chain_and_constraints() -> None:
    assert DATABASE_URL is not None
    token = uuid4().int
    provider_fixture_id = str(token % 8_000_000_000 + 1_000_000_000)
    fixture_id = f"api-football:{provider_fixture_id}"
    observed_at = datetime(2026, 9, 16, 12, tzinfo=UTC)
    fixture = Fixture(
        fixture_id=fixture_id,
        home_team="Home",
        away_team="Away",
        competition_id=39,
        competition_name="Premier League",
        country="England",
        kickoff_at=observed_at + timedelta(days=1),
        competition_type="League",
        season=2024,
        status="NS",
        provider="api-football",
        provider_fixture_id=provider_fixture_id,
        provider_home_team_id=1,
        provider_away_team_id=2,
    )
    _, artifact = trusted_artifact(TRAINED_AT + timedelta(seconds=token % 100_000))
    series_ids: list[str] = []
    snapshot_ids: list[str] = []
    prediction_id = ""
    evaluation_id = ""
    fixture_repo = PostgreSQLFixtureRepository(database_url=DATABASE_URL)
    prediction_repo = PostgreSQLFixturePredictionRepository(database_url=DATABASE_URL)
    quote_repo = PostgreSQLQuoteHistoryRepository(database_url=DATABASE_URL)
    evaluation_repo = PostgreSQLValueEvaluationRepository(database_url=DATABASE_URL)
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            apply_migrations(connection, MIGRATION_DIR)
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT version FROM schema_migrations WHERE version = %s",
                    ("004_fixture_prediction_value_evaluation.sql",),
                )
                assert cursor.fetchone() == (
                    "004_fixture_prediction_value_evaluation.sql",
                )
        PostgreSQLDixonColesModelVersionRepository(database_url=DATABASE_URL).add(artifact)

        # Quote history may exist before the durable fixture anchor.
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
        series_ids.extend(item.series_id for item in series)
        for item in series:
            snapshot_ids.extend(
                s.snapshot_id for s in quote_repo.snapshots_for_series(item.series_id)
            )

        durable = fixture_repo.record_discovery(fixture, observed_at=observed_at)
        assert fixture_repo.record_discovery(fixture, observed_at=observed_at) == durable
        with pytest.raises(FixturePersistenceConflictError):
            fixture_repo.record_discovery(
                Fixture(
                    **{
                        name: getattr(fixture, name)
                        for name in fixture.__dataclass_fields__
                        if name != "fixture_id"
                    },
                    fixture_id=f"api-football:{int(provider_fixture_id) + 1}",
                ),
                observed_at=observed_at,
            )

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
            over_2_5_probability=0.6,
            under_2_5_probability=0.4,
            btts_yes_probability=0.55,
            predicted_at=observed_at,
            persisted_at=observed_at,
        )
        prediction = prediction_repo.add(prediction)
        prediction_id = prediction.prediction_id
        assert prediction_repo.add(prediction) == prediction

        selected = next(
            quote_repo.snapshots_for_series(item.series_id)[0]
            for item in series
            if item.selection is Selection.OVER
        )
        evaluator = EvaluatePersistedPredictionQuote(
            prediction_repo, quote_repo, evaluation_repo, clock=lambda: observed_at
        )
        evaluation = evaluator.execute(prediction.prediction_id, selected.snapshot_id)
        evaluation_id = evaluation.evaluation_id
        assert evaluator.execute(prediction.prediction_id, selected.snapshot_id) == evaluation
        assert evaluation.selected_devig_probability == pytest.approx(0.47368421052631576)
    finally:
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            if evaluation_id:
                cursor.execute(
                    "DELETE FROM value_evaluations WHERE evaluation_id = %s", (evaluation_id,)
                )
            if prediction_id:
                cursor.execute(
                    "DELETE FROM fixture_predictions WHERE prediction_id = %s", (prediction_id,)
                )
            if snapshot_ids:
                cursor.execute(
                    "DELETE FROM quote_snapshots WHERE snapshot_id = ANY(%s)", (snapshot_ids,)
                )
            if series_ids:
                cursor.execute("DELETE FROM quote_series WHERE series_id = ANY(%s)", (series_ids,))
            cursor.execute("DELETE FROM fixture_observations WHERE fixture_id = %s", (fixture_id,))
            cursor.execute("DELETE FROM fixtures WHERE fixture_id = %s", (fixture_id,))
            cursor.execute(
                "DELETE FROM dixon_coles_model_versions WHERE model_version_id = %s "
                "AND NOT EXISTS (SELECT 1 FROM dixon_coles_active_models WHERE model_version_id = %s)",
                (artifact.model_version_id, artifact.model_version_id),
            )
