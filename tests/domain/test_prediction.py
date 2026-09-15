from datetime import UTC, datetime

import numpy as np
import pytest

from h2h.domain import FixturePrediction, PredictionTarget
from h2h.domain.fixture import Fixture
from h2h.domain.fixture_identity import api_football_fixture_identity
from h2h.quant import DixonColesModel
from h2h.use_cases import DixonColesFixturePredictor


def fixture(
    *,
    fixture_id: str = "api-football:123",
    provider: str = "api-football",
    provider_fixture_id: str | None = "123",
    home_team: str = "Home",
    away_team: str = "Away",
    home_team_id: int | None = 101,
    away_team_id: int | None = 202,
) -> Fixture:
    return Fixture(
        fixture_id=fixture_id,
        home_team=home_team,
        away_team=away_team,
        competition_id=39,
        competition_name="Premier League",
        country="England",
        kickoff_at=datetime(2026, 9, 17, 18, tzinfo=UTC),
        provider=provider,
        provider_fixture_id=provider_fixture_id,
        provider_home_team_id=home_team_id,
        provider_away_team_id=away_team_id,
    )


def model() -> DixonColesModel:
    return DixonColesModel(
        team_ids=(101, 202),
        team_id_namespace="api-football",
        attacks=np.zeros(2),
        defenses=np.zeros(2),
        intercept=0.0,
        home_advantage=0.1,
        rho=0.0,
        xi=0.0015,
        fitted_matches=80,
        objective=1.0,
    )


def predict(authoritative_fixture: Fixture):
    return DixonColesFixturePredictor(model()).predict(authoritative_fixture)


def test_public_prediction_interfaces_are_not_constructible() -> None:
    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        PredictionTarget()  # type: ignore[misc]
    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        FixturePrediction()  # type: ignore[misc]


def test_target_from_fixture_retains_canonical_identity_namespace_and_team_order() -> None:
    target = predict(fixture()).target

    assert target.fixture_identity == api_football_fixture_identity(123)
    assert target.fixture_id == "api-football:123"
    assert target.team_id_namespace == "api-football"
    assert (target.home_team_id, target.away_team_id) == (101, 202)


@pytest.mark.parametrize(
    "field,expected_message",
    [
        ("home", "provider_home_team_id"),
        ("away", "provider_away_team_id"),
    ],
)
def test_target_rejects_missing_ordered_team_id(
    field: str,
    expected_message: str,
) -> None:
    kwargs = {"home_team_id": 101, "away_team_id": 202}
    kwargs[f"{field}_team_id"] = None

    with pytest.raises(ValueError, match=expected_message):
        predict(fixture(**kwargs))  # type: ignore[arg-type]


def test_target_rejects_missing_provider_fixture_identity() -> None:
    with pytest.raises(ValueError, match="provider_fixture_id"):
        predict(fixture(provider_fixture_id=None))


def test_target_rejects_contradictory_canonical_and_provider_fixture_identity() -> None:
    with pytest.raises(ValueError, match="does not match"):
        predict(fixture(fixture_id="api-football:999"))


def test_target_never_uses_team_names_as_identity_fallback() -> None:
    named_like_ids = fixture(
        home_team="101",
        away_team="202",
        home_team_id=None,
        away_team_id=None,
    )

    with pytest.raises(ValueError, match="provider_home_team_id"):
        predict(named_like_ids)


def test_target_rejects_equal_home_and_away_team_ids() -> None:
    with pytest.raises(ValueError, match="must be different"):
        predict(fixture(home_team_id=101, away_team_id=101))


def test_fixture_prediction_copies_and_freezes_probabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = {"OVER_2_5": 0.4, "UNDER_2_5": 0.6, "BTTS_YES": 0.5}

    def probabilities(*args: object, **kwargs: object) -> dict[str, float]:
        return source

    monkeypatch.setattr(DixonColesModel, "market_probabilities", probabilities)
    prediction = predict(fixture())

    source["OVER_2_5"] = 0.9
    assert prediction.probabilities["OVER_2_5"] == 0.4
    with pytest.raises(TypeError):
        prediction.probabilities["OVER_2_5"] = 0.9  # type: ignore[index]
    with pytest.raises(AttributeError):
        prediction.target = prediction.target  # type: ignore[misc]


@pytest.mark.parametrize(
    "probabilities",
    [
        {"OVER_2_5": 0.5, "UNDER_2_5": 0.5},
        {"OVER_2_5": float("nan"), "UNDER_2_5": 0.5, "BTTS_YES": 0.5},
        {"OVER_2_5": 1.1, "UNDER_2_5": -0.1, "BTTS_YES": 0.5},
    ],
)
def test_predictor_rejects_invalid_probability_results(
    probabilities: dict[str, float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        DixonColesModel,
        "market_probabilities",
        lambda *args, **kwargs: probabilities,
    )

    with pytest.raises(ValueError):
        predict(fixture())
