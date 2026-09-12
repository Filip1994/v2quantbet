from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from h2h.quant.dixon_coles import DixonColesFitError, DixonColesModel


@dataclass(frozen=True, slots=True)
class Record:
    date: datetime
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int


def records_for_teams(team_ids: tuple[int, ...], count: int = 20) -> list[Record]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    records: list[Record] = []
    for index in range(count):
        home_id = team_ids[index % len(team_ids)]
        away_id = team_ids[(index + 1) % len(team_ids)]
        if home_id == away_id:
            away_id = team_ids[(index + 2) % len(team_ids)]
        records.append(
            Record(
                date=start + timedelta(days=index),
                home_id=home_id,
                away_id=away_id,
                home_goals=index % 3,
                away_goals=(index + 1) % 2,
            )
        )
    return records


def fitted_model() -> DixonColesModel:
    return DixonColesModel.fit(
        records_for_teams((1, 2, 3, 4), count=40),
        reference_time=datetime(2025, 1, 1, tzinfo=UTC),
        xi=0.0015,
        min_matches=1,
    )


def test_fit_rejects_insufficient_training_matches() -> None:
    records = records_for_teams((1, 2, 3, 4), count=3)
    with pytest.raises(DixonColesFitError, match="Premalo trening mečeva"):
        DixonColesModel.fit(
            records,
            reference_time=datetime(2025, 1, 1, tzinfo=UTC),
            xi=0.0015,
            min_matches=4,
        )


def test_fit_rejects_fewer_than_four_teams() -> None:
    records = records_for_teams((1, 2, 3), count=12)
    with pytest.raises(DixonColesFitError, match="najmanje četiri povezana tima"):
        DixonColesModel.fit(
            records,
            reference_time=datetime(2025, 1, 1, tzinfo=UTC),
            xi=0.0015,
            min_matches=1,
        )


def test_fit_excludes_matches_at_or_after_reference_time() -> None:
    records = records_for_teams((1, 2, 3, 4), count=12)
    reference_time = records[-1].date
    model = DixonColesModel.fit(
        records,
        reference_time=reference_time,
        xi=0.0015,
        min_matches=1,
    )
    assert model.fitted_matches == len(records) - 1


def test_expected_goals_rejects_unknown_team() -> None:
    model = fitted_model()
    with pytest.raises(DixonColesFitError, match="ne postoji u trening uzorku"):
        model.expected_goals(1, 99)


def test_score_matrix_is_finite_and_normalized() -> None:
    matrix = fitted_model().score_matrix(1, 2, max_goals=12)
    assert matrix.shape == (13, 13)
    assert np.isfinite(matrix).all()
    assert (matrix >= 0.0).all()
    assert np.isclose(matrix.sum(), 1.0)


def test_market_probabilities_are_bounded_and_over_under_complementary() -> None:
    probabilities = fitted_model().market_probabilities(1, 2, max_goals=12)
    assert set(probabilities) == {"OVER_2_5", "UNDER_2_5", "BTTS_YES"}
    assert all(0.0 <= value <= 1.0 for value in probabilities.values())
    assert np.isclose(
        probabilities["OVER_2_5"] + probabilities["UNDER_2_5"],
        1.0,
    )


def test_fit_and_predictions_are_deterministic() -> None:
    first = fitted_model()
    second = fitted_model()
    np.testing.assert_allclose(first.attacks, second.attacks)
    np.testing.assert_allclose(first.defenses, second.defenses)
    assert first.intercept == second.intercept
    assert first.home_advantage == second.home_advantage
    assert first.rho == second.rho
    assert first.objective == second.objective
    np.testing.assert_allclose(
        first.score_matrix(1, 2, max_goals=12),
        second.score_matrix(1, 2, max_goals=12),
    )
