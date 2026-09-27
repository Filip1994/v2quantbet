from datetime import UTC, datetime, timedelta

import numpy as np

from h2h.quantlab.goal_lab.model import (
    FIT_FTOL,
    FIT_GTOL,
    FIT_MAX_ITER,
    _fit_dc_plus,
)


def test_dc_plus_optimizer_converges_with_recorded_diagnostics() -> None:
    n = 320
    teams = np.asarray([1, 2, 3, 4], dtype=np.int64)
    home_ids = np.resize(teams, n)
    away_ids = np.resize(np.roll(teams, 1), n)
    league_ids = np.ones(n, dtype=np.int64)
    dates = np.asarray(
        [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(n)],
        dtype=object,
    )
    x = np.column_stack(
        (
            np.sin(np.arange(n, dtype=float) / 11.0),
            np.cos(np.arange(n, dtype=float) / 17.0),
        )
    )
    y_home = np.asarray([1 + (index % 3 == 0) for index in range(n)], dtype=float)
    y_away = np.asarray([index % 4 == 0 for index in range(n)], dtype=float)

    fitted = _fit_dc_plus(
        x,
        y_home,
        y_away,
        home_ids,
        away_ids,
        league_ids,
        dates,
        ("form_signal", "pressure_signal"),
        reference_time=dates[-1],
    )

    assert fitted is not None
    payload, objective = fitted
    optimizer = payload["optimizer"]
    assert optimizer["method"] == "L-BFGS-B"
    assert optimizer["maxiter"] == FIT_MAX_ITER == 300
    assert optimizer["ftol"] == FIT_FTOL == 1e-7
    assert optimizer["gtol"] == FIT_GTOL == 1e-4
    assert optimizer["iterations"] <= FIT_MAX_ITER
    assert np.isfinite(optimizer["gradient_inf_norm"])
    assert np.isfinite(objective)
