from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.prediction_record import PersistedFixturePrediction
from h2h.domain.value_evaluation import PROPORTIONAL_TWO_WAY_V1, ValueEvaluation
from h2h.persistence.postgres_predictions import PostgreSQLFixturePredictionRepository
from h2h.persistence.postgres_value_evaluations import PostgreSQLValueEvaluationRepository
from h2h.persistence.predictions import PredictionPersistenceConflictError
from h2h.persistence.value_evaluations import ValueEvaluationPersistenceConflictError


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def execute(self, sql, params=None):
        params = tuple(params or ())
        rows = self.connection.rows
        if sql.startswith("INSERT INTO fixture_predictions"):
            natural = (params[2], params[3], params[4], params[12], params[13])
            if not any(
                row[0] == params[0] or (row[2], row[3], row[4], row[12], row[13]) == natural
                for row in rows
            ):
                rows.append(params)
            self.row = None
        elif "FROM fixture_predictions WHERE prediction_id" in sql:
            self.row = next((row for row in rows if row[0] == params[0]), None)
        elif "FROM fixture_predictions WHERE fixture_observation_id" in sql:
            self.row = next(
                (row for row in rows if (row[2], row[3], row[4], row[12], row[13]) == params),
                None,
            )
        elif sql.startswith("INSERT INTO value_evaluations"):
            natural = (params[2], params[6], params[7], params[22])
            if not any(
                row[0] == params[0] or (row[2], row[6], row[7], row[22]) == natural for row in rows
            ):
                rows.append(params)
            self.row = None
        elif "FROM value_evaluations WHERE evaluation_id" in sql:
            self.row = next((row for row in rows if row[0] == params[0]), None)
        elif "FROM value_evaluations WHERE prediction_id" in sql:
            self.row = next(
                (row for row in rows if (row[2], row[6], row[7], row[22]) == params),
                None,
            )
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.rows = []
        self.rollback_seen = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.rollback_seen = exc_type is not None
        return False

    def cursor(self):
        return FakeCursor(self)


def prediction():
    return PersistedFixturePrediction(
        prediction_id="fixture-prediction-v1:" + "a" * 64,
        fixture_id="api-football:123",
        fixture_observation_id="fixture-observation-v1:" + "b" * 64,
        model_version_id="dcm-json-v1:" + "c" * 64,
        active_generation=1,
        model_activated_at=NOW,
        provider="api-football",
        team_id_namespace="api-football",
        league_id=39,
        season=2026,
        provider_home_team_id=10,
        provider_away_team_id=20,
        prediction_method_version="DIXON_COLES_MARKET_PROBABILITIES_V1",
        max_goals=10,
        over_2_5_probability=0.6,
        under_2_5_probability=0.4,
        btts_yes_probability=0.55,
        predicted_at=NOW,
        persisted_at=NOW,
    )


def evaluation():
    selected_raw, companion_raw = 0.5, 1 / 1.8
    overround = selected_raw + companion_raw
    fair = selected_raw / overround
    return ValueEvaluation(
        evaluation_id="value-evaluation-v1:" + "d" * 64,
        fixture_id="api-football:123",
        prediction_id=prediction().prediction_id,
        model_version_id=prediction().model_version_id,
        selected_series_id="series-over",
        companion_series_id="series-under",
        selected_snapshot_id="snapshot-over",
        companion_snapshot_id="snapshot-under",
        bookmaker_id=8,
        bookmaker_key="bet365",
        market=Market.OU_25,
        selected_selection=Selection.OVER,
        companion_selection=Selection.UNDER,
        quote_observed_at=NOW,
        source="api-football",
        selected_captured_at=NOW,
        companion_captured_at=NOW,
        selected_odd=2.0,
        companion_odd=1.8,
        selected_raw_implied_probability=selected_raw,
        companion_raw_implied_probability=companion_raw,
        overround=overround,
        devig_method_version=PROPORTIONAL_TWO_WAY_V1,
        selected_devig_probability=fair,
        model_probability=0.6,
        edge=0.6 - fair,
        expected_value=0.2,
        evaluated_at=NOW,
        persisted_at=NOW,
    )


def test_prediction_repository_reconstructs_replays_and_rolls_back_conflicts() -> None:
    connection = FakeConnection()
    repository = PostgreSQLFixturePredictionRepository(connect=lambda: connection)
    first = repository.add(prediction())
    retry = replace(
        prediction(),
        predicted_at=NOW + timedelta(minutes=1),
        persisted_at=NOW + timedelta(minutes=1),
    )
    assert repository.add(retry) == first
    assert repository.get(first.prediction_id) == first
    with pytest.raises(PredictionPersistenceConflictError):
        repository.add(replace(prediction(), over_2_5_probability=0.7))
    assert connection.rollback_seen


def test_prediction_repository_rejects_natural_key_race_with_different_id() -> None:
    connection = FakeConnection()
    repository = PostgreSQLFixturePredictionRepository(connect=lambda: connection)
    repository.add(prediction())
    with pytest.raises(PredictionPersistenceConflictError):
        repository.add(replace(prediction(), prediction_id="fixture-prediction-v1:" + "f" * 64))


def test_evaluation_repository_reconstructs_replays_and_revalidates_arithmetic() -> None:
    connection = FakeConnection()
    repository = PostgreSQLValueEvaluationRepository(connect=lambda: connection)
    first = repository.add(evaluation())
    retry = replace(
        evaluation(),
        evaluated_at=NOW + timedelta(minutes=1),
        persisted_at=NOW + timedelta(minutes=1),
    )
    assert repository.add(retry) == first
    assert repository.get(first.evaluation_id) == first
    row = list(connection.rows[0])
    row[25] += 0.01
    connection.rows[0] = tuple(row)
    with pytest.raises(ValueError, match="contradicts"):
        repository.get(first.evaluation_id)


def test_evaluation_repository_conflicting_replay_rolls_back() -> None:
    connection = FakeConnection()
    repository = PostgreSQLValueEvaluationRepository(connect=lambda: connection)
    repository.add(evaluation())
    changed = replace(
        evaluation(),
        model_probability=0.61,
        edge=0.61 - evaluation().selected_devig_probability,
        expected_value=0.22,
    )
    with pytest.raises(ValueEvaluationPersistenceConflictError):
        repository.add(changed)
    assert connection.rollback_seen
