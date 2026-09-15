import inspect
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

import h2h.use_cases.fixture_prediction as fixture_prediction_module
from h2h.domain import FixturePrediction, PredictionTarget
from h2h.domain.fixture import Fixture
from h2h.domain.fixture_identity import api_football_fixture_identity
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.quant.dixon_coles import DixonColesFitError, DixonColesModel
from h2h.use_cases import (
    DixonColesFixturePredictor,
    PredictionFixtureMismatchError,
    TeamIdNamespaceMismatchError,
    evaluate_prediction_quote,
)


def fixture(
    *,
    fixture_id: str = "api-football:123",
    provider_fixture_id: str = "123",
    home_team_id: int = 101,
    away_team_id: int = 202,
) -> Fixture:
    return Fixture(
        fixture_id=fixture_id,
        home_team="Home",
        away_team="Away",
        competition_id=39,
        competition_name="Premier League",
        country="England",
        kickoff_at=datetime(2026, 9, 17, 18, tzinfo=UTC),
        provider="api-football",
        provider_fixture_id=provider_fixture_id,
        provider_home_team_id=home_team_id,
        provider_away_team_id=away_team_id,
    )


def model(*, namespace: str = "api-football") -> DixonColesModel:
    return DixonColesModel(
        team_ids=(101, 202),
        team_id_namespace=namespace,
        attacks=np.zeros(2),
        defenses=np.zeros(2),
        intercept=0.0,
        home_advantage=0.1,
        rho=0.0,
        xi=0.0015,
        fitted_matches=80,
        objective=1.0,
    )


def quote(*, fixture_id: str = "api-football:123") -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id=fixture_id,
        bookmaker_id=8,
        bookmaker_name="Bet365",
        market=Market.OU_25,
        selection=Selection.OVER,
        odd=2.0,
        observed_at=datetime(2026, 9, 16, 12, tzinfo=UTC),
        source="api-football",
    )


def fixed_prediction() -> FixturePrediction:
    return DixonColesFixturePredictor(model()).predict(fixture())


def test_matching_namespace_predicts_and_retains_exact_target() -> None:
    authoritative_fixture = fixture()

    prediction = DixonColesFixturePredictor(model()).predict(authoritative_fixture)

    assert prediction.target.fixture_id == "api-football:123"
    assert prediction.target.fixture_identity == api_football_fixture_identity(123)
    assert (prediction.target.home_team_id, prediction.target.away_team_id) == (101, 202)
    assert set(prediction.probabilities) == {"OVER_2_5", "UNDER_2_5", "BTTS_YES"}


def test_namespace_mismatch_fails_before_model_probability_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def record_call(*args: object, **kwargs: object) -> dict[str, float]:
        nonlocal called
        called = True
        return {"OVER_2_5": 0.5, "UNDER_2_5": 0.5, "BTTS_YES": 0.5}

    monkeypatch.setattr(DixonColesModel, "market_probabilities", record_call)

    with pytest.raises(TeamIdNamespaceMismatchError, match="namespace"):
        DixonColesFixturePredictor(model(namespace="other-provider")).predict(fixture())

    assert not called


def test_predictor_passes_home_and_away_in_authoritative_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int]] = []

    def record_call(
        self: DixonColesModel,
        home_id: int,
        away_id: int,
        max_goals: int = 10,
    ) -> dict[str, float]:
        calls.append((home_id, away_id, max_goals))
        return {"OVER_2_5": 0.5, "UNDER_2_5": 0.5, "BTTS_YES": 0.5}

    monkeypatch.setattr(DixonColesModel, "market_probabilities", record_call)

    DixonColesFixturePredictor(model()).predict(fixture(), max_goals=12)

    assert calls == [(101, 202, 12)]


def test_unknown_target_team_uses_existing_model_failure() -> None:
    with pytest.raises(DixonColesFitError, match="ne postoji"):
        DixonColesFixturePredictor(model()).predict(
            fixture(home_team_id=999),
        )


def test_reversing_teams_changes_target_and_execution_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def record_call(
        self: DixonColesModel,
        home_id: int,
        away_id: int,
        max_goals: int = 10,
    ) -> dict[str, float]:
        calls.append((home_id, away_id))
        return {"OVER_2_5": 0.5, "UNDER_2_5": 0.5, "BTTS_YES": 0.5}

    monkeypatch.setattr(DixonColesModel, "market_probabilities", record_call)
    predictor = DixonColesFixturePredictor(model())

    first = predictor.predict(fixture(home_team_id=101, away_team_id=202))
    reversed_prediction = predictor.predict(
        fixture(home_team_id=202, away_team_id=101),
    )

    assert first.target != reversed_prediction.target
    assert calls == [(101, 202), (202, 101)]


def test_predictor_has_no_fixture_identity_override_argument() -> None:
    assert list(inspect.signature(DixonColesFixturePredictor.predict).parameters) == [
        "self",
        "fixture",
        "max_goals",
    ]


def test_matching_canonical_fixture_prediction_and_quote_can_be_valued() -> None:
    prediction = fixed_prediction()
    result = evaluate_prediction_quote(prediction, quote())

    assert result.quote.fixture_id == "api-football:123"
    assert result.model_probability == prediction.probabilities["OVER_2_5"]
    assert result.implied_probability == 0.5
    assert result.probability_gap == pytest.approx(result.model_probability - 0.5)
    assert result.expected_value == pytest.approx(result.model_probability * 2.0 - 1.0)


def test_public_api_cannot_rebind_genuine_fixture_a_probabilities_to_fixture_b() -> None:
    predictor = DixonColesFixturePredictor(model())
    prediction_a = predictor.predict(fixture())
    prediction_b = predictor.predict(
        fixture(fixture_id="api-football:456", provider_fixture_id="456")
    )

    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        FixturePrediction(  # type: ignore[misc]
            target=prediction_b.target,
            probabilities=prediction_a.probabilities,
        )
    with pytest.raises(TypeError, match="created by the fixture predictor"):
        type(prediction_a)(
            target=prediction_b.target,
            probabilities=prediction_a.probabilities,
        )
    with pytest.raises(TypeError, match="created by the fixture predictor"):
        replace(
            prediction_a,
            target=prediction_b.target,
            probabilities=prediction_a.probabilities,
        )


def test_public_api_cannot_manufacture_valuation_accepted_prediction() -> None:
    arbitrary_target = object()
    arbitrary_probabilities = {
        "OVER_2_5": 0.9,
        "UNDER_2_5": 0.1,
        "BTTS_YES": 0.8,
    }

    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        PredictionTarget(  # type: ignore[misc]
            fixture_identity=api_football_fixture_identity(456),
            home_team_id=303,
            away_team_id=404,
        )
    genuine_target = fixed_prediction().target
    with pytest.raises(TypeError, match="created by the fixture predictor"):
        type(genuine_target)(
            fixture_identity=api_football_fixture_identity(456),
            home_team_id=303,
            away_team_id=404,
        )
    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        FixturePrediction(  # type: ignore[misc]
            target=arbitrary_target,
            probabilities=arbitrary_probabilities,
        )
    with pytest.raises(TypeError, match="produced by DixonColesFixturePredictor"):
        evaluate_prediction_quote(arbitrary_target, quote())  # type: ignore[arg-type]


def test_equal_fixture_team_ids_fail_before_model_probability_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def record_call(*args: object, **kwargs: object) -> dict[str, float]:
        nonlocal called
        called = True
        return {"OVER_2_5": 0.5, "UNDER_2_5": 0.5, "BTTS_YES": 0.5}

    monkeypatch.setattr(DixonColesModel, "market_probabilities", record_call)

    with pytest.raises(ValueError, match="must be different"):
        DixonColesFixturePredictor(model()).predict(
            fixture(home_team_id=101, away_team_id=101)
        )

    assert not called


@pytest.mark.parametrize(
    "quote_fixture_id",
    ["api-football:999", "123", "other-provider:123"],
)
def test_nonmatching_fixture_identity_cannot_be_valued(
    quote_fixture_id: str,
) -> None:
    with pytest.raises(PredictionFixtureMismatchError, match="same canonical fixture"):
        evaluate_prediction_quote(
            fixed_prediction(),
            quote(fixture_id=quote_fixture_id),
        )


def test_fixture_mismatch_fails_before_probability_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def record_call(*args: object, **kwargs: object) -> float:
        nonlocal called
        called = True
        return 0.5

    monkeypatch.setattr(
        fixture_prediction_module,
        "model_probability_for_selection",
        record_call,
    )

    with pytest.raises(PredictionFixtureMismatchError):
        evaluate_prediction_quote(
            fixed_prediction(),
            quote(fixture_id="api-football:456"),
        )

    assert not called
