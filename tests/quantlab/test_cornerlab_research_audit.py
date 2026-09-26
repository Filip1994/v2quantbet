from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isfinite

from h2h.quantlab.corner_lab.research_audit import (
    STANDARD_HALF_LINES,
    run_cornerlab_historical_holdout,
)


NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _history_rows(count: int = 180) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    start = NOW - timedelta(days=count + 5)
    for index in range(count):
        home = 1
        away = 2
        home_possession = 47.0 + (index % 9)
        away_possession = 100.0 - home_possession
        home_shots = 9 + (index % 7)
        away_shots = 8 + ((index * 3) % 6)
        home_sot = 3 + (index % 5)
        away_sot = 2 + ((index + 2) % 5)
        home_corners = 3 + (index % 5)
        away_corners = 2 + ((index * 2 + 1) % 5)
        kickoff = start + timedelta(days=index)

        rows.append(
            {
                "fixture_id": f"api-football:{50000 + index}",
                "kickoff_at": kickoff,
                "available_at": kickoff + timedelta(hours=3),
                "competition_name": "Synthetic League",
                "home_team_id": home,
                "away_team_id": away,
                "home_corner_kicks": home_corners,
                "away_corner_kicks": away_corners,
                "home_ball_possession": home_possession,
                "away_ball_possession": away_possession,
                "home_shots_on_goal": home_sot,
                "away_shots_on_goal": away_sot,
                "home_total_shots": home_shots,
                "away_total_shots": away_shots,
                "home_blocked_shots": 2 + index % 3,
                "away_blocked_shots": 1 + index % 4,
                "home_shots_insidebox": 5 + index % 6,
                "away_shots_insidebox": 4 + index % 5,
                "home_offsides": 1 + index % 3,
                "away_offsides": 1 + (index + 1) % 3,
                "home_total_passes": 390 + (index % 8) * 13,
                "away_total_passes": 370 + (index % 7) * 11,
                "home_passes_accurate": 315 + (index % 8) * 11,
                "away_passes_accurate": 295 + (index % 7) * 9,
                "home_pass_accuracy": 78.0 + index % 8,
                "away_pass_accuracy": 76.0 + (index + 3) % 9,
            }
        )
    return tuple(rows)


def test_historical_holdout_is_chronological_and_scores_future_rows() -> None:
    result = run_cornerlab_historical_holdout(_history_rows())

    assert result["status"] == "OK"
    assert result["train_training_examples"] >= 80
    assert result["holdout_predictions"] >= 30
    assert result["train_history_matches"] < result["history_rows"]
    assert result["bookmaker_split"]["status"] == "NOT_AVAILABLE"

    summary = result["summary"]
    assert summary["n"] == result["holdout_predictions"]
    assert summary["observed_mean"] > 0
    assert summary["predicted_mean"] > 0
    assert summary["mae"] >= 0
    assert summary["rmse"] >= summary["mae"]
    assert isfinite(summary["poisson_log_likelihood"])
    assert isfinite(summary["mean_poisson_log_likelihood"])
    assert summary["variance_to_mean"] >= 0
    assert summary["pearson_dispersion"] >= 0

    lines = result["line_calibration_over"]
    assert tuple(item["line"] for item in lines) == STANDARD_HALF_LINES
    assert all(item["n"] == result["holdout_predictions"] for item in lines)
    assert all(0 <= item["brier"] <= 1 for item in lines)
    assert all(item["log_loss"] >= 0 for item in lines)

    comparison = result["poisson_vs_nb2"]
    assert comparison["status"] == "OK"
    assert comparison["nb2_alpha"] > 0
    assert comparison["nb2_size"] > 0
    assert comparison["research_signal"] in {
        "NB2_DISTRIBUTION_PROMISING",
        "POISSON_DISTRIBUTION_PREFERRED",
        "MIXED_DISTRIBUTION_SIGNAL",
    }
    assert len(comparison["line_comparison"]) == len(STANDARD_HALF_LINES)
    assert isfinite(comparison["count_log_likelihood"]["poisson_mean"])
    assert isfinite(comparison["count_log_likelihood"]["nb2_mean"])


def test_historical_holdout_rejects_small_history() -> None:
    result = run_cornerlab_historical_holdout(_history_rows(70))

    assert result["status"] == "INSUFFICIENT_HOLDOUT_TRAINING_SAMPLE"
    assert result["history_rows"] == 70
    assert result["minimum_training_examples"] == 80
