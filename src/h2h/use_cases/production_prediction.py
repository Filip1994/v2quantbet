"""Production prediction from durable fixture and validated active model."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from h2h.domain.fixture import Fixture
from h2h.domain.fixture_identity import API_FOOTBALL_PROVIDER
from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.domain.prediction_record import PersistedFixturePrediction
from h2h.persistence.fixtures import FixtureRepository
from h2h.persistence.predictions import FixturePredictionRepository
from h2h.use_cases.fixture_prediction import DixonColesFixturePredictor
from h2h.use_cases.model_lifecycle import LoadActiveDixonColesModel


PREDICTION_METHOD_VERSION = "DIXON_COLES_MARKET_PROBABILITIES_V1"


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _prediction_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "fixture-prediction-v1:" + sha256(encoded).hexdigest()


class ProduceFixturePrediction:
    def __init__(
        self,
        fixtures: FixtureRepository,
        active_models: LoadActiveDixonColesModel,
        predictions: FixturePredictionRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._fixtures = fixtures
        self._active_models = active_models
        self._predictions = predictions
        self._clock = clock

    def execute(self, fixture_id: str, *, max_goals: int = 10) -> PersistedFixturePrediction:
        if isinstance(max_goals, bool) or not isinstance(max_goals, int) or max_goals <= 0:
            raise ValueError("max_goals must be a positive integer")
        persisted_fixture = self._fixtures.get(fixture_id)
        if persisted_fixture is None:
            raise LookupError(f"durable fixture {fixture_id!r} does not exist")
        identity, observation = persisted_fixture.identity, persisted_fixture.observation
        if identity.provider != API_FOOTBALL_PROVIDER:
            raise ValueError("production prediction supports only api-football fixtures")
        scope = DixonColesModelScope(
            provider=identity.provider,
            team_id_namespace=API_FOOTBALL_PROVIDER,
            league_id=identity.league_id,
            season=identity.season,
        )
        selected = self._active_models.execute_with_selection(scope)
        if selected.scope != scope:
            raise ValueError("active model scope does not match durable fixture scope")
        if selected.loaded.model.team_id_namespace != scope.team_id_namespace:
            raise ValueError("active model namespace does not match durable fixture namespace")
        fixture = Fixture(
            fixture_id=identity.fixture_id,
            home_team=observation.home_team,
            away_team=observation.away_team,
            competition_id=identity.league_id,
            competition_name=observation.competition_name,
            country=observation.country,
            kickoff_at=observation.kickoff_at,
            competition_type=observation.competition_type,
            season=identity.season,
            status=observation.provider_status,
            provider=identity.provider,
            provider_fixture_id=identity.provider_fixture_id,
            provider_home_team_id=identity.provider_home_team_id,
            provider_away_team_id=identity.provider_away_team_id,
        )
        result = DixonColesFixturePredictor(selected.loaded.model).predict(
            fixture, max_goals=max_goals
        )
        if (
            result.target.fixture_id != identity.fixture_id
            or result.target.team_id_namespace != scope.team_id_namespace
            or result.target.home_team_id != identity.provider_home_team_id
            or result.target.away_team_id != identity.provider_away_team_id
        ):
            raise ValueError("controlled prediction target contradicts durable fixture")
        predicted_at = _now(self._clock)
        semantic = {
            "active_generation": selected.generation,
            "fixture_observation_id": observation.fixture_observation_id,
            "max_goals": max_goals,
            "model_version_id": selected.model_version_id,
            "prediction_method_version": PREDICTION_METHOD_VERSION,
        }
        prediction = PersistedFixturePrediction(
            prediction_id=_prediction_id(semantic),
            fixture_id=identity.fixture_id,
            fixture_observation_id=observation.fixture_observation_id,
            model_version_id=selected.model_version_id,
            active_generation=selected.generation,
            model_activated_at=selected.activated_at,
            provider=identity.provider,
            team_id_namespace=scope.team_id_namespace,
            league_id=identity.league_id,
            season=identity.season,
            provider_home_team_id=identity.provider_home_team_id,
            provider_away_team_id=identity.provider_away_team_id,
            prediction_method_version=PREDICTION_METHOD_VERSION,
            max_goals=max_goals,
            over_2_5_probability=result.probabilities["OVER_2_5"],
            under_2_5_probability=result.probabilities["UNDER_2_5"],
            btts_yes_probability=result.probabilities["BTTS_YES"],
            predicted_at=predicted_at,
            persisted_at=predicted_at,
        )
        return self._predictions.add(prediction)
