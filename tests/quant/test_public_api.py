import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from h2h.quant import DixonColesFitError, DixonColesModel, dixon_coles_tau
from h2h.quant.dixon_coles import DixonColesFitError as ModuleFitError
from h2h.quant.dixon_coles import DixonColesModel as ModuleModel
from h2h.quant.dixon_coles import dixon_coles_tau as module_tau


@dataclass(frozen=True)
class MatchRecord:
    date: datetime
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int


def _records() -> list[MatchRecord]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        MatchRecord(
            date=start + timedelta(days=index),
            home_id=(index % 4) + 1,
            away_id=((index + 1) % 4) + 1,
            home_goals=index % 3,
            away_goals=(index + 1) % 2,
        )
        for index in range(80)
    ]


def test_public_quant_exports_are_canonical() -> None:
    assert DixonColesModel is ModuleModel
    assert DixonColesFitError is ModuleFitError
    assert dixon_coles_tau is module_tau


def test_public_tau_function_is_callable() -> None:
    assert dixon_coles_tau(0, 0, 1.4, 1.1, -0.05) == 1.077


def test_fit_signature_is_keyword_only_after_records() -> None:
    signature = inspect.signature(DixonColesModel.fit)
    assert list(signature.parameters) == [
        "records",
        "team_id_namespace",
        "reference_time",
        "xi",
        "ridge",
        "min_matches",
    ]
    assert signature.parameters["reference_time"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["xi"].kind is inspect.Parameter.KEYWORD_ONLY


def test_fitted_model_exposes_contract_attributes_and_prediction_shapes() -> None:
    model = DixonColesModel.fit(
        _records(),
        team_id_namespace="synthetic-test",
        reference_time=datetime(2025, 1, 1, tzinfo=UTC),
        xi=0.001,
        min_matches=80,
    )

    assert isinstance(model.team_ids, tuple)
    assert model.team_id_namespace == "synthetic-test"
    assert model.fitted_matches == 80
    assert np.isfinite(model.objective)
    assert model.attacks.shape == model.defenses.shape == (4,)

    expected_goals = model.expected_goals(1, 2)
    assert len(expected_goals) == 2
    assert all(np.isfinite(value) and value > 0 for value in expected_goals)

    matrix = model.score_matrix(1, 2, max_goals=6)
    assert matrix.shape == (7, 7)
    assert np.all(np.isfinite(matrix))
    assert np.all(matrix >= 0)
    assert np.isclose(matrix.sum(), 1.0)

    markets = model.market_probabilities(1, 2, max_goals=6)
    assert set(markets) == {"OVER_2_5", "UNDER_2_5", "BTTS_YES"}
    assert all(0.0 <= value <= 1.0 for value in markets.values())
    assert np.isclose(markets["OVER_2_5"] + markets["UNDER_2_5"], 1.0)


def test_prediction_for_unknown_team_uses_public_fit_error() -> None:
    model = DixonColesModel.fit(
        _records(),
        team_id_namespace="synthetic-test",
        reference_time=datetime(2025, 1, 1, tzinfo=UTC),
        xi=0.001,
        min_matches=80,
    )

    with pytest.raises(DixonColesFitError):
        model.expected_goals(1, 999)


def test_team_match_counts_is_available_as_model_api() -> None:
    counts = DixonColesModel.team_match_counts(_records())
    assert sum(counts.values()) == 160
    assert set(counts) == {1, 2, 3, 4}
