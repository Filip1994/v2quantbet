from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from h2h.quantlab.goal_lab.readiness import (
    GOALLAB_V1_LOCK_VERSION,
    LOCKED_CONTRACT,
    assert_goallab_v1_contract,
)
from h2h.quantlab.goal_lab.structural_shadow_engine import (
    GoalLabStructuralShadowEngine,
    StructuralGoalPolicy,
)
from h2h.quantlab.runtime import QuantLabRuntime


NOW = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
NEW_MODEL = "DC_PLUS_PRO_STRUCTURAL_V1:" + "2" * 64
OLD_MODEL = "DC_PLUS_PRO_STRUCTURAL_V1:" + "1" * 64


def _fixture(
    fixture_id: str = "api-football:9001",
    *,
    league_id: int = 39,
    competition_name: str = "Premier League",
    country: str = "England",
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "provider_fixture_id": int(fixture_id.split(":")[-1]),
        "league_id": league_id,
        "season": 2026,
        "home_team_id": 1,
        "away_team_id": 2,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": competition_name,
        "country": country,
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
            "OVER": {"market_observation_id": "obs-over", "odds": 2.0},
            "UNDER": {"market_observation_id": "obs-under", "odds": 1.8},
        },
    }


class ReadyModel:
    def estimate(self, _fixture, *, decision_at):
        assert decision_at == NOW
        artifact = SimpleNamespace(
            model_version=NEW_MODEL,
            rho=-0.04,
            feature_version="GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1",
            training_sample_size=600,
            history_match_count=900,
        )
        snapshot = SimpleNamespace(
            home_history_size=15,
            away_history_size=14,
            feature_snapshot_id="quantlab-goal-features-v1:" + "a" * 64,
        )
        estimate = SimpleNamespace(
            expected_home_goals=2.1,
            expected_away_goals=1.0,
            model=artifact,
            snapshot=snapshot,
            market_probabilities=lambda: {
                "OVER_2_5": 0.72,
                "UNDER_2_5": 0.28,
                "BTTS_YES": 0.58,
            },
        )
        return SimpleNamespace(estimate=estimate, reason="MODEL_READY", details={})


class EngineRepo:
    def __init__(self) -> None:
        self.decisions = []
        self.picks = []

    def goal_market_pairs(self, _fixture_id, *, decision_at):
        assert decision_at == NOW
        return (_pair(),)

    def goal_model_validation(self, _model_version):
        return {
            "status": "OK",
            "authority_review_status": "READY_FOR_MANUAL_REVIEW",
            "leakage_audit": {"status": "PASS"},
        }

    def goal_pick_exists(self, _fixture_id, *, pick_policy_version):
        assert pick_policy_version == "GOALLAB_DC_PLUS_PICK_POLICY_V1"
        return False

    def save_goal_decision(self, item):
        self.decisions.append(item)
        return True

    def save_goal_pick(self, item):
        self.picks.append(item)
        return True


def test_goallab_v1_contract_is_frozen() -> None:
    contract = assert_goallab_v1_contract()

    assert contract == LOCKED_CONTRACT
    assert contract["lock_version"] == GOALLAB_V1_LOCK_VERSION
    assert contract["canonical_markets"] == ("OU_25", "BTTS")


def test_goallab_v1_lock_fails_closed_on_semantic_drift(monkeypatch) -> None:
    import h2h.quantlab.goal_lab.readiness as readiness

    monkeypatch.setattr(readiness, "MIN_EDGE", 0.031)

    with pytest.raises(RuntimeError, match="contract drift"):
        readiness.assert_goallab_v1_contract()


def test_retrain_pauses_authority_when_only_old_model_is_approved() -> None:
    repo = EngineRepo()
    engine = GoalLabStructuralShadowEngine(
        repo,
        policy=StructuralGoalPolicy(
            pick_authority=True,
            approved_model_version=OLD_MODEL,
        ),
    )
    engine._model = ReadyModel()

    result = engine.run_fixture(_fixture(), decision_at=NOW)

    assert result.picks_inserted == 0
    assert repo.picks == []
    canonical = [
        item
        for item in repo.decisions
        if item.details.get("canonical_fixture_candidate") is True
    ]
    assert len(canonical) == 1
    assert canonical[0].decision == "PASS"
    assert canonical[0].reason == "CANONICAL_FIXTURE_AWAITING_MODEL_APPROVAL"
    assert canonical[0].details["model_approved"] is False
    assert canonical[0].details["authority_gate"] == "MODEL_VERSION_APPROVAL_REQUIRED"


@pytest.mark.parametrize(
    ("fixture_id", "league_id", "competition_name", "country"),
    (
        ("api-football:9101", 39, "Premier League", "England"),
        ("api-football:9102", 140, "La Liga", "Spain"),
        ("api-football:9103", 135, "Serie A", "Italy"),
    ),
)
def test_real_league_fixture_flows_to_one_canonical_pick(
    fixture_id,
    league_id,
    competition_name,
    country,
) -> None:
    repo = EngineRepo()
    engine = GoalLabStructuralShadowEngine(
        repo,
        policy=StructuralGoalPolicy(
            pick_authority=True,
            approved_model_version=NEW_MODEL,
        ),
    )
    engine._model = ReadyModel()

    result = engine.run_fixture(
        _fixture(
            fixture_id,
            league_id=league_id,
            competition_name=competition_name,
            country=country,
        ),
        decision_at=NOW,
    )

    assert result.picks_inserted == 1
    assert len(repo.picks) == 1
    assert repo.picks[0].fixture_id == fixture_id
    assert repo.picks[0].model_version == NEW_MODEL
    assert repo.picks[0].pick_policy_version == "GOALLAB_DC_PLUS_PICK_POLICY_V1"


def test_runtime_isolates_one_goal_fixture_failure_and_continues(caplog) -> None:
    fixtures = (
        _fixture("api-football:9201"),
        _fixture("api-football:9202"),
    )

    class Repo:
        def upcoming_fixtures(self, **_kwargs):
            return fixtures

    class Engine:
        def run_fixture(self, fixture, *, decision_at):
            assert decision_at == NOW
            if fixture["fixture_id"] == "api-football:9201":
                raise ValueError("malformed evidence")
            return SimpleNamespace(decisions_inserted=3, picks_inserted=1)

    runtime = QuantLabRuntime(Repo(), object(), goal_engine=Engine())

    with caplog.at_level(logging.ERROR):
        decisions, picks = runtime._evaluate_goal_picks(NOW)

    assert (decisions, picks) == (3, 1)
    assert "GoalLab fixture evaluation failed fixture=api-football:9201" in caplog.text


def test_runtime_isolates_one_goal_settlement_failure_and_continues(caplog) -> None:
    valid = {
        "goal_pick_id": "quantlab-goal-pick-v1:" + "b" * 64,
        "fixture_id": "api-football:9302",
        "market_key": "OU_25",
        "selection": "OVER",
        "line": 2.5,
        "odds": 2.0,
        "stake_minor": 10_000,
        "result_classification": "PLAYED_SETTLEABLE",
        "regulation_home_goals": 2,
        "regulation_away_goals": 1,
        "result_observation_id": "result-2",
    }
    invalid = dict(valid)
    invalid["goal_pick_id"] = "quantlab-goal-pick-v1:" + "c" * 64
    invalid["fixture_id"] = "api-football:9301"
    invalid["market_key"] = "UNSUPPORTED"

    class Repo:
        def goal_pick_settlement_candidates(self, *, limit):
            assert limit == 500
            return (invalid, valid)

        def save_goal_pick_settlement(self, _settlement):
            return True

    runtime = QuantLabRuntime(Repo(), object())

    with caplog.at_level(logging.ERROR):
        settled = runtime._settle_goal_picks(NOW)

    assert settled == 1
    assert "GoalLab settlement failed fixture=api-football:9301" in caplog.text
