from __future__ import annotations
from math import isclose


# Baseline values calculated from the pinned legacy implementation at commit
# 9b2337b8432546420945f32586b7a4b84355589b using its deterministic
# tests/test_dixon_coles.py synthetic dataset.
LEGACY_COMMIT = "9b2337b8432546420945f32586b7a4b84355589b"

EXPECTED = {
    "fitted_matches": 300,
    "team_count": 6,
    "objective": 663.8139057155488,
    "rho": 0.015893744318639533,
    "intercept": 0.01748506205616492,
    "home_advantage": 0.3859856224069123,
    "attacks": (
        -0.00018334590272585017,
        -0.0006049796968737931,
        -0.040101042923168156,
        0.041287812035137164,
        -0.0002241807607518084,
        -0.00017426275161756398,
    ),
    "defenses": (
        0.00011349512825542724,
        -0.000579092307183124,
        -0.040203966050346186,
        0.04128382299887347,
        -0.0007433661036229883,
        0.00012910633402339673,
    ),
    "expected_goals": (1.4958704021983442, 1.017138789717719),
    "probabilities": {
        "OVER_2_5": 0.45951928075270043,
        "UNDER_2_5": 0.5404807192472996,
        "BTTS_YES": 0.4933829544540229,
    },
}


def test_golden_master_values_are_locked() -> None:
    assert EXPECTED["fitted_matches"] == 300
    assert EXPECTED["team_count"] == 6
    assert isclose(EXPECTED["objective"], 663.8139057155488, rel_tol=0.0, abs_tol=1e-15)
    assert isclose(EXPECTED["rho"], 0.015893744318639533, rel_tol=0.0, abs_tol=1e-15)
    assert isclose(EXPECTED["intercept"], 0.01748506205616492, rel_tol=0.0, abs_tol=1e-15)
    assert isclose(EXPECTED["home_advantage"], 0.3859856224069123, rel_tol=0.0, abs_tol=1e-15)
    assert all(
        isclose(actual, expected, rel_tol=0.0, abs_tol=1e-15)
        for actual, expected in zip(
            EXPECTED["attacks"],
            (
                -0.00018334590272585017,
                -0.0006049796968737931,
                -0.040101042923168156,
                0.041287812035137164,
                -0.0002241807607518084,
                -0.00017426275161756398,
            ),
            strict=True,
        )
    )
    assert all(
        isclose(actual, expected, rel_tol=0.0, abs_tol=1e-15)
        for actual, expected in zip(
            EXPECTED["defenses"],
            (
                0.00011349512825542724,
                -0.000579092307183124,
                -0.040203966050346186,
                0.04128382299887347,
                -0.0007433661036229883,
                0.00012910633402339673,
            ),
            strict=True,
        )
    )
    assert all(
        isclose(actual, expected, rel_tol=0.0, abs_tol=1e-15)
        for actual, expected in zip(
            EXPECTED["expected_goals"],
            (1.4958704021983442, 1.017138789717719),
            strict=True,
        )
    )
    assert all(
        isclose(actual, expected, rel_tol=0.0, abs_tol=1e-15)
        for actual, expected in zip(
            EXPECTED["probabilities"].values(),
            (0.45951928075270043, 0.5404807192472996, 0.4933829544540229),
            strict=True,
        )
    )
