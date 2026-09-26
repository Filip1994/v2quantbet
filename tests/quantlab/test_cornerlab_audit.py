from __future__ import annotations

import pytest

from h2h.quantlab.corner_lab.audit import _calibration, _quality


def test_cornerlab_quality_uses_precomputed_expected_and_actual_totals() -> None:
    result = _quality(
        (
            {
                "actual_total_corners": 10,
                "expected_total_corners": 11,
                "competition_name": "League A",
            },
            {
                "actual_total_corners": 12,
                "expected_total_corners": 11,
                "competition_name": "League A",
            },
        )
    )

    assert result["n"] == 2
    assert result["observed_mean"] == 11.0
    assert result["predicted_mean"] == 11.0
    assert result["mae"] == 1.0
    assert result["rmse"] == 1.0
    assert result["observed_variance"] == 2.0
    assert result["residual_variance"] == 2.0


def test_cornerlab_calibration_scores_over_probability_once_per_sample() -> None:
    result = _calibration(
        (
            {
                "fixture_id": "fixture-1",
                "model_probability": 0.7,
                "line": 10.5,
                "actual_total_corners": 11,
                "bookmaker_name": "Bet365",
                "competition_name": "League A",
            },
            {
                "fixture_id": "fixture-2",
                "model_probability": 0.3,
                "line": 10.5,
                "actual_total_corners": 10,
                "bookmaker_name": "1xBet",
                "competition_name": "League A",
            },
        )
    )

    overall = result["overall"]
    assert overall["n"] == 2
    assert overall["mean_model_probability"] == 0.5
    assert overall["observed_over_rate"] == 0.5
    assert overall["brier"] == pytest.approx(0.09)
    assert overall["log_loss"] == pytest.approx(0.356675, abs=1e-6)
