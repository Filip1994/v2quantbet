from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np

from h2h.quantlab.goal_lab import model


def test_latent_team_support_requires_minimum_training_appearances() -> None:
    home = np.asarray([1, 1, 1, 1, 1, 1], dtype=np.int64)
    away = np.asarray([2, 2, 2, 2, 2, 3], dtype=np.int64)

    latent, support = model._latent_team_support(home, away, minimum_matches=5)

    assert latent == (1, 2)
    assert support == {1: 6, 2: 5, 3: 1}


def test_dc_plus_keeps_sparse_team_coverage_with_neutral_latent_effect(
    monkeypatch,
) -> None:
    n = model.MIN_TRAINING_EXAMPLES
    home_ids = np.ones(n, dtype=np.int64)
    away_ids = np.full(n, 2, dtype=np.int64)
    away_ids[-1] = 3
    x = np.zeros((n, 1), dtype=float)
    y_home = np.ones(n, dtype=float)
    y_away = np.ones(n, dtype=float)
    league_ids = np.full(n, 39, dtype=np.int64)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    dates = np.asarray([start + timedelta(days=i) for i in range(n)], dtype=object)

    captured = {}

    def fake_minimize(_objective, initial, **kwargs):
        captured["parameter_count"] = len(initial)
        captured["options"] = kwargs["options"]
        return SimpleNamespace(
            success=True,
            fun=1.0,
            x=np.asarray(initial, dtype=float),
            jac=np.zeros_like(initial),
            status=0,
            message="ok",
            nit=1,
            nfev=1,
        )

    monkeypatch.setattr(model, "minimize", fake_minimize)
    fitted = model._fit_dc_plus(
        x,
        y_home,
        y_away,
        home_ids,
        away_ids,
        league_ids,
        dates,
        ("feature",),
        reference_time=dates[-1],
    )

    assert fitted is not None
    params, _objective = fitted
    assert params["latent_team_ids"] == (1, 2)
    assert params["attacks"]["3"] == 0.0
    assert params["defenses"]["3"] == 0.0
    assert params["team_training_appearances"]["3"] == 1
    assert captured["parameter_count"] == 10
    assert captured["options"] == {
        "maxiter": model.OPTIMIZER_MAXITER,
        "ftol": model.OPTIMIZER_FTOL,
        "gtol": model.OPTIMIZER_GTOL,
    }
    assert model.OPTIMIZER_MAXITER == 1400
    assert model.OPTIMIZER_GTOL == 1e-5


def test_v2_feature_contract_is_compact_and_predeclared() -> None:
    rows = []
    for index in range(120):
        rows.append(
            {
                "home_l5_goals_for": 1.0 + index * 0.001,
                "away_l5_goals_against": 1.2 + index * 0.001,
                "home_l5_shots_for": 10.0 + index * 0.01,
                "away_l5_sot_against": 4.0 + index * 0.01,
                "noise_feature_should_not_enter_model": 99.0,
            }
        )

    x, model_names, _means, _scales, base_names = model._prepare_features(rows)

    assert "noise_feature_should_not_enter_model" not in model_names
    assert model_names == base_names
    assert x.shape[1] == len(model_names)
    assert x.shape[1] <= len(model.V2_CORE_FEATURE_NAMES)
    assert all(not name.endswith("__missing") for name in model_names)


def test_v2_regularization_is_stronger_than_v1_contract() -> None:
    assert model.RIDGE_TEAM > 1.5
    assert model.RIDGE_FEATURE > 4.0
    assert model.RIDGE_INTERACTION > 8.0
