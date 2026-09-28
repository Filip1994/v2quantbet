from __future__ import annotations

from h2h.quantlab.goal_lab.explanations import build_goal_pick_explanation


MODEL = "DC_PLUS_PRO_STRUCTURAL_V1:" + "a" * 64


def _row() -> dict[str, object]:
    return {
        "goal_pick_id": "quantlab-goal-pick-v1:" + "b" * 64,
        "home_team": "Home",
        "away_team": "Away",
        "market_key": "OU_25",
        "selection": "OVER",
        "bookmaker_name": "Bet365",
        "odds": 2.0,
        "model_probability": 0.58,
        "market_probability": 0.52,
        "edge": 0.06,
        "expected_value": 0.16,
        "expected_home_goals": 1.70,
        "expected_away_goals": 1.10,
        "model_version": MODEL,
        "feature_payload": {
            "raw_features": {
                "home_l5_goals_for": 2.10,
                "home_l5_goals_against": 1.00,
                "away_l5_goals_for": 1.20,
                "away_l5_goals_against": 1.60,
                "home_l5_shots_for": 14.0,
                "home_l5_sot_for": 5.4,
                "away_l5_shots_for": 10.2,
                "away_l5_sot_for": 3.6,
                "home_rest_days": 6.0,
                "away_rest_days": 3.0,
            },
            "model_feature_names": (
                "home_l5_goals_for",
                "away_l5_goals_against",
            ),
            "target_match_live_stats_used": False,
        },
        "selection_rank_payload": {
            "candidate_count": 3,
            "candidates": [
                {
                    "rank": 1,
                    "bookmaker_name": "Bet365",
                    "market_key": "OU_25",
                    "selection": "OVER",
                }
            ],
        },
    }


def _contract() -> dict[str, object]:
    return {
        "model_version": MODEL,
        "parameters": {
            "model_feature_names": (
                "home_l5_goals_for",
                "away_l5_goals_against",
            ),
            "base_feature_names": (
                "home_l5_goals_for",
                "away_l5_goals_against",
            ),
            "beta_home": [0.20, 0.10],
            "beta_away": [0.05, 0.30],
        },
        "feature_means": {
            "home_l5_goals_for": 1.50,
            "away_l5_goals_against": 1.20,
        },
        "feature_scales": {
            "home_l5_goals_for": 0.50,
            "away_l5_goals_against": 0.40,
        },
    }


def test_goal_pick_explanation_uses_exact_persisted_numbers() -> None:
    explanation = build_goal_pick_explanation(_row(), _contract())

    assert "58.0%" in explanation["summary"]
    assert "52.0%" in explanation["summary"]
    assert "+6.0 pp" in explanation["summary"]
    assert "1.70 gola za domaćina" in explanation["summary"]
    assert "1.10 za gosta" in explanation["summary"]
    assert any(
        line.startswith("Forma golova L5: domaćin daje 2.10")
        for line in explanation["context_lines"]
    )
    assert any(
        line.startswith("Šutevi L5: domaćin 14.00")
        for line in explanation["context_lines"]
    )
    assert any(
        line.startswith("Odmor i raspored: domaćin odmara 6.0 dana")
        for line in explanation["context_lines"]
    )
    assert explanation["ranking"] is not None
    assert "Među 3 kandidata" in explanation["ranking"]


def test_goal_pick_explanation_reconstructs_numeric_model_contributions() -> None:
    explanation = build_goal_pick_explanation(_row(), _contract())

    contributions = {
        item["feature"]: item for item in explanation["all_contributions"]
    }
    home_form = contributions["home_l5_goals_for"]
    away_defence = contributions["away_l5_goals_against"]

    assert home_form["raw_value"] == 2.10
    assert home_form["training_mean"] == 1.50
    assert round(home_form["standardized"], 3) == 1.2
    assert round(home_form["home_eta_contribution"], 3) == 0.24
    assert round(home_form["away_eta_contribution"], 3) == 0.06

    assert away_defence["raw_value"] == 1.60
    assert away_defence["training_mean"] == 1.20
    assert round(away_defence["standardized"], 3) == 1.0
    assert round(away_defence["home_eta_contribution"], 3) == 0.10
    assert round(away_defence["away_eta_contribution"], 3) == 0.30
