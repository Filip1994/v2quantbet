from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from h2h.quantlab.corner_lab.model import (
    FEATURE_VERSION,
    MIN_TRAINING_EXAMPLES,
    CornerPressureModelService,
)


NOW = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)


def _history_rows(count: int = 220) -> tuple[dict[str, object], ...]:
    rows = []
    start = NOW - timedelta(days=count + 20)
    teams = tuple(range(1, 13))
    for index in range(count):
        home = teams[index % len(teams)]
        away = teams[(index * 5 + 3) % len(teams)]
        if away == home:
            away = teams[(teams.index(away) + 1) % len(teams)]

        home_attack = 8.0 + (home % 5) + (index % 4) * 0.7
        away_attack = 7.0 + (away % 4) + ((index + 2) % 5) * 0.5
        home_possession = 48.0 + (home % 5) * 2.0 + (index % 3)
        away_possession = 100.0 - home_possession
        home_shots = round(home_attack + 4)
        away_shots = round(away_attack + 3)
        home_sot = max(2, round(home_shots * 0.42))
        away_sot = max(2, round(away_shots * 0.40))
        home_corners = 2 + int(home_shots / 4) + int(home_possession >= 54) + index % 2
        away_corners = 2 + int(away_shots / 4) + int(away_possession >= 52) + (index + 1) % 2

        rows.append(
            {
                "fixture_id": f"api-football:{10000 + index}",
                "kickoff_at": start + timedelta(days=index),
                "available_at": start + timedelta(days=index, hours=3),
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
                "home_blocked_shots": max(1, home_shots // 4),
                "away_blocked_shots": max(1, away_shots // 4),
                "home_shots_insidebox": max(2, int(home_shots * 0.65)),
                "away_shots_insidebox": max(2, int(away_shots * 0.62)),
                "home_offsides": 1 + home % 3,
                "away_offsides": 1 + away % 3,
                "home_total_passes": int(360 + home_possession * 3.2),
                "away_total_passes": int(360 + away_possession * 3.2),
                "home_passes_accurate": int(300 + home_possession * 2.8),
                "away_passes_accurate": int(300 + away_possession * 2.8),
                "home_pass_accuracy": 76.0 + home % 10,
                "away_pass_accuracy": 76.0 + away % 10,
            }
        )
    return tuple(rows)


class Repo:
    def __init__(self):
        self.history = _history_rows()
        self.history_calls = 0
        self.models = []
        self.snapshots = []

    def corner_model_history(self, *, before, limit):
        assert before == NOW
        assert limit >= len(self.history)
        self.history_calls += 1
        return self.history

    def save_corner_model_version(self, item):
        self.models.append(item)
        return True

    def save_corner_feature_snapshot(self, item):
        self.snapshots.append(item)
        return item.fixture_id


def test_corner_pressure_model_fits_structural_history_and_persists_audit():
    repo = Repo()
    service = CornerPressureModelService(repo)
    fixture = {
        "fixture_id": "api-football:target",
        "home_team_id": 1,
        "away_team_id": 2,
    }

    result = service.estimate(fixture, decision_at=NOW)

    assert result.reason == "MODEL_READY"
    assert result.estimate is not None
    estimate = result.estimate
    assert estimate.model.feature_version == FEATURE_VERSION
    assert estimate.model.training_sample_size >= MIN_TRAINING_EXAMPLES
    assert estimate.model.model_version.startswith("CORNER_PRESSURE_POISSON_V1:")
    assert estimate.expected_total_corners > 0
    assert repo.models
    assert repo.snapshots

    raw = estimate.snapshot.feature_payload["raw_features"]
    assert raw["home_l5_possession"] is not None
    assert raw["home_l5_sot_for"] is not None
    assert raw["home_l5_inside_box_for"] is not None
    assert raw["home_l5_accurate_passes_for"] is not None
    assert raw["away_venue_l5_corners_against"] is not None

    over = estimate.probability("OVER", 10.5)
    under = estimate.probability("UNDER", 10.5)
    assert 0 < over < 1
    assert 0 < under < 1
    assert over + under == pytest.approx(1.0)


def test_corner_pressure_model_is_fitted_once_per_decision_cycle():
    repo = Repo()
    service = CornerPressureModelService(repo)

    first = service.estimate(
        {"fixture_id": "api-football:a", "home_team_id": 1, "away_team_id": 2},
        decision_at=NOW,
    )
    second = service.estimate(
        {"fixture_id": "api-football:b", "home_team_id": 3, "away_team_id": 4},
        decision_at=NOW,
    )

    assert first.estimate is not None
    assert second.estimate is not None
    assert repo.history_calls == 1
    assert first.estimate.model.model_version == second.estimate.model.model_version
