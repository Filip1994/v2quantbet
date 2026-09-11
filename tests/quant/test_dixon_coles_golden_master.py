from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isclose

from h2h.quant.dixon_coles import DixonColesModel, dixon_coles_tau

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


@dataclass(frozen=True, slots=True)
class SyntheticRecord:
    date: datetime
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int


def synthetic_records() -> list[SyntheticRecord]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    records: list[SyntheticRecord] = []
    fixture_id = 1
    teams = list(range(1, 7))
    for round_index in range(10):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                records.append(
                    SyntheticRecord(
                        date=start + timedelta(days=fixture_id),
                        home_id=home,
                        away_id=away,
                        home_goals=(home + round_index + away) % 4,
                        away_goals=(2 * away + round_index + home) % 3,
                    )
                )
                fixture_id += 1
    return records


def test_golden_master_values_are_locked() -> None:
    records = synthetic_records()
    reference = records[-1].date + timedelta(days=1)
    model = DixonColesModel.fit(records, reference_time=reference, xi=0.0015, min_matches=80)
    probabilities = model.market_probabilities(1, 2, max_goals=10)
    expected_goals = model.expected_goals(1, 2)

    assert model.fitted_matches == EXPECTED["fitted_matches"]
    assert len(model.team_ids) == EXPECTED["team_count"]
    assert isclose(model.objective, EXPECTED["objective"], rel_tol=0.0, abs_tol=1e-12)
    assert isclose(model.rho, EXPECTED["rho"], rel_tol=0.0, abs_tol=1e-12)
    assert isclose(model.intercept, EXPECTED["intercept"], rel_tol=0.0, abs_tol=1e-12)
    assert isclose(model.home_advantage, EXPECTED["home_advantage"], rel_tol=0.0, abs_tol=1e-12)
    assert all(
        isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)
        for actual, expected in zip(model.attacks, EXPECTED["attacks"], strict=True)
    )
    assert all(
        isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)
        for actual, expected in zip(model.defenses, EXPECTED["defenses"], strict=True)
    )
    assert all(
        isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)
        for actual, expected in zip(expected_goals, EXPECTED["expected_goals"], strict=True)
    )
    assert all(
        isclose(probabilities[market], expected, rel_tol=0.0, abs_tol=1e-12)
        for market, expected in EXPECTED["probabilities"].items()
    )


def test_tau_low_score_correction() -> None:
    assert dixon_coles_tau(0, 0, 1.4, 1.1, -0.05) == 1.077
    assert dixon_coles_tau(2, 1, 1.4, 1.1, -0.05) == 1.0
