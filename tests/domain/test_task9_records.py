from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from h2h.domain.fixture_record import FixtureIdentityRecord, FixtureObservation, PersistedFixture
from h2h.domain.odds import Market, Selection
from h2h.domain.prediction_record import PersistedFixturePrediction
from h2h.domain.value_evaluation import (
    PROPORTIONAL_TWO_WAY_V1,
    PersistedMarketObservation,
    PersistedQuoteObservation,
    ValueEvaluation,
)


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


def identity(**changes):
    values = {
        "fixture_id": "api-football:123",
        "provider": "api-football",
        "provider_fixture_id": "123",
        "league_id": 39,
        "season": 2026,
        "provider_home_team_id": 10,
        "provider_away_team_id": 20,
        "created_at": NOW,
    }
    values.update(changes)
    return FixtureIdentityRecord(**values)


def observation(**changes):
    values = {
        "fixture_observation_id": "fixture-observation-v1:" + "a" * 64,
        "fixture_id": "api-football:123",
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "League",
        "country": "England",
        "competition_type": "League",
        "kickoff_at": NOW + timedelta(days=1),
        "provider_status": "NS",
        "source": "api-football",
        "observed_at": NOW,
        "persisted_at": NOW,
    }
    values.update(changes)
    return FixtureObservation(**values)


def prediction(**changes):
    values = {
        "prediction_id": "fixture-prediction-v1:" + "b" * 64,
        "fixture_id": "api-football:123",
        "fixture_observation_id": observation().fixture_observation_id,
        "model_version_id": "dcm-json-v1:" + "c" * 64,
        "active_generation": 2,
        "model_activated_at": NOW,
        "provider": "api-football",
        "team_id_namespace": "api-football",
        "league_id": 39,
        "season": 2026,
        "provider_home_team_id": 10,
        "provider_away_team_id": 20,
        "prediction_method_version": "DIXON_COLES_MARKET_PROBABILITIES_V1",
        "max_goals": 10,
        "over_2_5_probability": 0.6,
        "under_2_5_probability": 0.4,
        "btts_yes_probability": 0.55,
        "predicted_at": NOW,
        "persisted_at": NOW,
    }
    values.update(changes)
    return PersistedFixturePrediction(**values)


def quote(selection, odd, suffix):
    return PersistedQuoteObservation(
        series_id=f"series-{suffix}",
        snapshot_id=f"snapshot-{suffix}",
        fixture_id="api-football:123",
        bookmaker_id=8,
        bookmaker_key="bet365",
        market=Market.OU_25,
        selection=selection,
        odd=odd,
        observed_at=NOW,
        captured_at=NOW,
        source="api-football",
    )


def test_fixture_identity_preserves_order_and_observation_must_match() -> None:
    durable = PersistedFixture(identity(), observation())
    assert (durable.identity.provider_home_team_id, durable.identity.provider_away_team_id) == (
        10,
        20,
    )
    with pytest.raises(ValueError, match="must be different"):
        identity(provider_away_team_id=10)
    with pytest.raises(ValueError, match="must match"):
        PersistedFixture(identity(), observation(fixture_id="api-football:999"))


def test_records_require_utc_and_finite_probabilities() -> None:
    with pytest.raises(ValueError, match="UTC"):
        identity(created_at=NOW.astimezone(timezone(timedelta(hours=2))))
    with pytest.raises(ValueError, match="finite"):
        prediction(over_2_5_probability=float("nan"))


def test_persisted_prediction_contains_complete_supported_model_output() -> None:
    value = prediction()
    assert value.probabilities == {
        "OVER_2_5": 0.6,
        "UNDER_2_5": 0.4,
        "BTTS_YES": 0.55,
    }


def test_two_way_proportional_devig_golden_values_and_semantics() -> None:
    market = PersistedMarketObservation(
        (quote(Selection.OVER, 2.0, "over"), quote(Selection.UNDER, 1.8, "under"))
    )
    selected, companion = market.selected("snapshot-over")
    raw_a, raw_b = 1 / selected.odd, 1 / companion.odd
    overround = raw_a + raw_b
    fair = raw_a / overround
    value = ValueEvaluation(
        evaluation_id="value-evaluation-v1:" + "d" * 64,
        fixture_id=selected.fixture_id,
        prediction_id=prediction().prediction_id,
        model_version_id=prediction().model_version_id,
        selected_series_id=selected.series_id,
        companion_series_id=companion.series_id,
        selected_snapshot_id=selected.snapshot_id,
        companion_snapshot_id=companion.snapshot_id,
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
        selected_raw_implied_probability=raw_a,
        companion_raw_implied_probability=raw_b,
        overround=overround,
        devig_method_version=PROPORTIONAL_TWO_WAY_V1,
        selected_devig_probability=fair,
        model_probability=0.6,
        edge=0.6 - fair,
        expected_value=0.2,
        evaluated_at=NOW,
        persisted_at=NOW,
    )
    assert value.selected_raw_implied_probability == 0.5
    assert value.selected_devig_probability != value.selected_raw_implied_probability
    assert value.edge == pytest.approx(0.6 - fair)
    assert value.expected_value == pytest.approx(0.2)
    with pytest.raises(ValueError, match="contradicts"):
        replace(value, edge=value.edge + 0.01)
