from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from h2h.quantlab.goal_lab.composite_engine import GoalLabCompositeEngine
from h2h.quantlab.goal_lab.model import (
    FEATURE_VERSION,
    GoalFeatureSnapshot,
    GoalStructuralEstimate,
    GoalStructuralModelArtifact,
    _build_training,
)
from h2h.quantlab.goal_lab.shadow_engine import GoalEngineResult
from h2h.quantlab.goal_lab.structural_shadow_engine import GoalLabStructuralShadowEngine


NOW = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)


def _history_row(index: int, *, home_goals: int, away_goals: int) -> dict[str, object]:
    return {
        "fixture_id": f"history-{index}",
        "league_id": 39,
        "season": 2026,
        "home_team_id": 1,
        "away_team_id": 2,
        "kickoff_at": NOW - timedelta(days=20 - index),
        "home_goals": home_goals,
        "away_goals": away_goals,
    }


def _fixture() -> dict[str, object]:
    return {
        "fixture_id": "api-football:9001",
        "provider_fixture_id": 9001,
        "league_id": 39,
        "season": 2026,
        "home_team_id": 1,
        "away_team_id": 2,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "Premier League",
        "country": "England",
        "competition_type": "League",
        "kickoff_at": NOW + timedelta(hours=4),
        "provider_status": "NS",
    }


def _pair() -> dict[str, object]:
    captured = NOW - timedelta(minutes=10)
    return {
        "bookmaker_id": 8,
        "bookmaker_name": "Bet365",
        "provider_bet_id": 5,
        "provider_bet_name": "Goals Over/Under",
        "market_key": "OU_25",
        "line": 2.5,
        "captured_at": captured,
        "selections": {
            "OVER": {
                "market_observation_id": "obs-over",
                "odds": 2.0,
                "provider_updated_at": captured,
            },
            "UNDER": {
                "market_observation_id": "obs-under",
                "odds": 1.8,
                "provider_updated_at": captured,
            },
        },
    }


def test_structural_training_features_do_not_include_target_result() -> None:
    rows = tuple(
        [_history_row(index, home_goals=1, away_goals=0) for index in range(5)]
        + [_history_row(5, home_goals=9, away_goals=9)]
    )

    (
        feature_rows,
        home_targets,
        away_targets,
        _home_ids,
        _away_ids,
        _league_ids,
        _dates,
        _histories,
        _pairs,
        usable_matches,
    ) = _build_training(rows)

    assert usable_matches == 6
    assert len(feature_rows) == 1
    assert home_targets.tolist() == [9.0]
    assert away_targets.tolist() == [9.0]
    assert feature_rows[0]["home_l3_goals_for"] == pytest.approx(1.0)
    assert feature_rows[0]["away_l3_goals_for"] == pytest.approx(0.0)


def test_structural_estimate_produces_bounded_goal_market_probabilities() -> None:
    artifact = GoalStructuralModelArtifact(
        model_version="DC_PLUS_PRO_STRUCTURAL_V1:" + "a" * 64,
        trained_at=NOW,
        training_cutoff=NOW,
        feature_version=FEATURE_VERSION,
        training_sample_size=500,
        history_match_count=700,
        team_count=20,
        league_count=1,
        ridge_team=1.5,
        ridge_feature=4.0,
        rho=-0.05,
        intercept=0.1,
        home_advantage=0.1,
        parameters={},
        feature_means={},
        feature_scales={},
        training_payload={},
    )
    snapshot = GoalFeatureSnapshot(
        fixture_id="fixture-1",
        decision_at=NOW,
        model_version=artifact.model_version,
        expected_home_goals=1.6,
        expected_away_goals=1.1,
        home_history_size=10,
        away_history_size=10,
        feature_payload={},
    )
    estimate = GoalStructuralEstimate(
        expected_home_goals=1.6,
        expected_away_goals=1.1,
        model=artifact,
        snapshot=snapshot,
    )

    probabilities = estimate.market_probabilities(max_goals=12)

    assert set(probabilities) == {"OVER_2_5", "UNDER_2_5", "BTTS_YES"}
    assert probabilities["OVER_2_5"] + probabilities["UNDER_2_5"] == pytest.approx(1.0)
    assert all(0.0 < value < 1.0 for value in probabilities.values())


def test_structural_value_signal_has_no_shadow_pick_authority() -> None:
    class Repo:
        def __init__(self) -> None:
            self.decisions = []
            self.shadow_calls = 0

        def goal_market_pairs(self, fixture_id, *, decision_at):
            assert fixture_id == "api-football:9001"
            assert decision_at == NOW
            return (_pair(),)

        def save_goal_decision(self, item):
            self.decisions.append(item)
            return True

        def save_goal_shadow_bet(self, *_args, **_kwargs):
            self.shadow_calls += 1
            raise AssertionError("Structural V1 must not create shadow bets")

    class Model:
        def estimate(self, _fixture, *, decision_at):
            assert decision_at == NOW
            artifact = SimpleNamespace(
                model_version="DC_PLUS_PRO_STRUCTURAL_V1:" + "b" * 64,
                rho=-0.05,
                feature_version=FEATURE_VERSION,
                training_sample_size=500,
                history_match_count=800,
            )
            snapshot = SimpleNamespace(home_history_size=12, away_history_size=11)
            estimate = SimpleNamespace(
                expected_home_goals=2.0,
                expected_away_goals=1.2,
                model=artifact,
                snapshot=snapshot,
                market_probabilities=lambda: {
                    "OVER_2_5": 0.70,
                    "UNDER_2_5": 0.30,
                    "BTTS_YES": 0.60,
                },
            )
            return SimpleNamespace(estimate=estimate, reason="MODEL_READY", details={})

    repo = Repo()
    engine = GoalLabStructuralShadowEngine(repo)
    engine._model = Model()

    result = engine.run_fixture(_fixture(), decision_at=NOW)

    assert result.picks_inserted == 0
    signals = [
        item for item in repo.decisions if item.reason == "STRUCTURAL_VALUE_SIGNAL_ONLY"
    ]
    assert len(signals) == 1
    assert signals[0].decision == "PASS"
    assert signals[0].selection == "OVER"
    assert signals[0].details["shadow_pick_authority"] is False
    assert repo.shadow_calls == 0


def test_composite_goal_engine_runs_control_and_structural_paths() -> None:
    class Engine:
        def __init__(self, decisions: int) -> None:
            self.decisions = decisions
            self.calls = 0

        def run_fixture(self, _fixture, *, decision_at):
            assert decision_at == NOW
            self.calls += 1
            return GoalEngineResult(decisions_inserted=self.decisions, picks_inserted=0)

    control = Engine(2)
    structural = Engine(3)
    result = GoalLabCompositeEngine(control, structural).run_fixture(
        _fixture(), decision_at=NOW
    )

    assert control.calls == 1
    assert structural.calls == 1
    assert result.decisions_inserted == 5
    assert result.picks_inserted == 0
