from datetime import UTC, datetime, timedelta

from h2h.quantlab.goal_analytics import (
    build_goal_analytics_snapshot,
    render_goal_analytics_html,
    render_goal_model_html,
    render_goal_pick_html,
)


NOW = datetime(2026, 9, 28, 0, tzinfo=UTC)
MODEL = "DC_PLUS_PRO_STRUCTURAL_V1:" + "a" * 64


def _pick(outcome: str = "WIN") -> dict:
    return {
        "goal_pick_id": "quantlab-goal-pick-v1:" + "b" * 64,
        "fixture_id": "api-football:1",
        "model_version": MODEL,
        "policy_version": "GOALLAB_DC_PLUS_PICK_POLICY_V1",
        "market_key": "OU_25",
        "selection": "OVER",
        "bookmaker_name": "Bet365",
        "competition_name": "Premier League",
        "kickoff_at": NOW - timedelta(days=1),
        "stake_minor": 10_000,
        "odds": 2.0,
        "model_probability": 0.60,
        "market_probability": 0.52,
        "edge": 0.08,
        "expected_value": 0.20,
        "expected_home_goals": 1.8,
        "expected_away_goals": 1.0,
        "outcome": outcome,
        "pnl_minor": 10_000 if outcome == "WIN" else -10_000,
        "home_team": "Home",
        "away_team": "Away",
        "feature_payload": {
            "raw_features": {"home_l5_goals_for": 1.7, "away_l5_goals_for": 1.1},
            "provenance": {"standings": "snapshot-1"},
        },
        "selection_rank_payload": {"expected_value": 0.20, "rank": 1},
    }


def test_goal_analytics_tracks_decision_funnel_and_model_cohorts() -> None:
    decisions = (
        {
            "fixture_id": "api-football:1",
            "decision": "PASS",
            "reason": "EDGE_BELOW_MINIMUM",
            "model_version": MODEL,
            "policy_version": "GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V2",
        },
        {
            "fixture_id": "api-football:2",
            "decision": "PICK",
            "reason": "CANONICAL_FIXTURE_VALUE_PICK",
            "model_version": MODEL,
            "policy_version": "GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V2",
        },
    )
    snapshot = build_goal_analytics_snapshot((_pick(),), decisions, as_of=NOW)

    assert snapshot["contract_version"] == "GOALLAB_ANALYTICS_V1"
    assert snapshot["windows"]["lifetime"]["wins"] == 1
    assert snapshot["windows"]["lifetime"]["roi_pct"] == 100.0
    assert snapshot["decision_funnel"][0]["rows"] == 1
    assert snapshot["decision_models"][0]["model_version"] == MODEL
    assert snapshot["cohorts"]["model_version"][0]["model_version"] == MODEL


def test_goal_analytics_html_exposes_research_style_sections() -> None:
    snapshot = build_goal_analytics_snapshot((_pick(),), (), as_of=NOW)
    html = render_goal_analytics_html(snapshot)

    assert "GoalLab Analytics" in html
    assert "Decision funnel" in html
    assert "Model versions · settled canonical picks" in html
    assert "/quantlab/goal/model?" in html


def test_goal_pick_drilldown_shows_exact_feature_payload() -> None:
    html = render_goal_pick_html(_pick())

    assert "Exact decision feature payload" in html
    assert "raw_features.home_l5_goals_for" in html
    assert "Canonical candidate ranking payload" in html


def test_goal_model_drilldown_shows_active_features_and_picks() -> None:
    contract = {
        "model_version": MODEL,
        "training_sample_size": 1277,
        "history_match_count": 10000,
        "active_feature_count": 2,
        "active_feature_names": ("home_l5_goals_for", "away_l5_goals_for"),
        "rho": -0.05,
        "training_payload": {
            "latent_team_count": 120,
            "minimum_latent_team_matches": 5,
        },
        "validation": {
            "status": "OK",
            "authority_review_status": "READY_FOR_MANUAL_REVIEW",
        },
    }
    html = render_goal_model_html(contract, (_pick(),))

    assert "1277" in html
    assert "home_l5_goals_for" in html
    assert "Latent teams" in html
    assert "120" in html
    assert "Latent min N" in html
    assert "READY_FOR_MANUAL_REVIEW" in html
    assert "/quantlab/goal/pick?" in html
