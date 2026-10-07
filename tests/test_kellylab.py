from datetime import UTC, datetime, timedelta

import pytest

from h2h.api.kellylab_dashboard import KellyLabDashboardService
from h2h.kellylab import (
    calibration_snapshot,
    kelly_stake_plan,
    pnl_minor,
)


NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


def _row(
    *,
    outcome: str = "WIN",
    model_probability: float = 0.55,
    odds: float = 2.0,
    edge: float = 0.10,
):
    row = {
        "market": "BTTS",
        "selection": "YES",
        "model_probability": model_probability,
        "odds": odds,
        "edge": edge,
    }
    if outcome == "WIN":
        row.update(
            {
                "result_classification": "PLAYED_SETTLEABLE",
                "regulation_home_goals": 1,
                "regulation_away_goals": 1,
            }
        )
    elif outcome == "LOSS":
        row.update(
            {
                "result_classification": "PLAYED_SETTLEABLE",
                "regulation_home_goals": 1,
                "regulation_away_goals": 0,
            }
        )
    else:
        row.update(
            {
                "result_classification": "NON_PLAYED_VOIDABLE",
                "regulation_home_goals": None,
                "regulation_away_goals": None,
            }
        )
    return row


def test_quarter_kelly_with_one_percent_cap_uses_300_rsd_from_30k_bankroll() -> None:
    plan = kelly_stake_plan(
        bankroll_minor=3_000_000,
        odds=2.0,
        probability=0.55,
    )

    assert float(plan["raw_kelly_fraction"]) == pytest.approx(0.10)
    assert float(plan["fractional_kelly_fraction"]) == pytest.approx(0.025)
    assert float(plan["applied_kelly_fraction"]) == pytest.approx(0.01)
    assert plan["stake_minor"] == 30_000
    assert plan["decision"] == "BET"


def test_negative_kelly_becomes_no_bet() -> None:
    plan = kelly_stake_plan(
        bankroll_minor=3_000_000,
        odds=1.90,
        probability=0.50,
    )

    assert plan["stake_minor"] == 0
    assert plan["decision"] == "NO_BET"
    assert float(plan["applied_kelly_fraction"]) == 0.0


def test_point_in_time_bucket_calibration_shrinks_gap_toward_zero() -> None:
    candidate = _row(model_probability=0.55, odds=2.0, edge=0.10)
    prior = [
        _row(outcome="WIN", model_probability=0.55, odds=2.0, edge=0.10)
        for _ in range(10)
    ]

    snapshot = calibration_snapshot(candidate, prior, prior_n=100)

    assert snapshot["combined_calibration_gap"] > 0
    assert snapshot["combined_calibration_gap"] < 0.45
    assert snapshot["kelly_probability"] > 0.55
    assert len(snapshot["dimensions"]) == 4
    assert all(item["n"] == 10 for item in snapshot["dimensions"])


def test_no_prior_evidence_keeps_model_probability() -> None:
    candidate = _row(model_probability=0.57)

    snapshot = calibration_snapshot(candidate, [], prior_n=100)

    assert snapshot["combined_calibration_gap"] == 0
    assert snapshot["kelly_probability"] == pytest.approx(0.57)


def test_kelly_pnl_uses_frozen_stake_and_entry_odds() -> None:
    assert pnl_minor(stake_minor=30_000, odds=2.10, outcome="WIN") == 33_000
    assert pnl_minor(stake_minor=30_000, odds=2.10, outcome="LOSS") == -30_000
    assert pnl_minor(stake_minor=30_000, odds=2.10, outcome="VOID") == 0
    assert pnl_minor(stake_minor=30_000, odds=2.10, outcome="PENDING") is None


class FakeRepository:
    def portfolio_snapshot(self):
        return {
            "portfolio": {
                "portfolio_id": "KELLYLAB_RESEARCH_V1",
                "started_at": NOW,
                "starting_bankroll_minor": 3_000_000,
                "flat_stake_minor": 30_000,
                "kelly_fraction": 0.25,
                "max_bet_fraction": 0.01,
                "calibration_prior_n": 100,
                "currency": "RSD",
                "pick_count": 1,
                "bet_count": 1,
                "no_bet_count": 0,
                "settled_count": 0,
                "active_count": 1,
                "open_stake_minor": 30_000,
                "kelly_pnl_minor": 0,
                "flat_pnl_minor": 0,
                "kelly_bankroll_minor": 3_000_000,
                "flat_bankroll_minor": 3_000_000,
                "kelly_return_pct": 0.0,
                "flat_return_pct": 0.0,
                "kelly_max_drawdown_pct": 0.0,
                "flat_max_drawdown_pct": 0.0,
            },
            "picks": [
                {
                    "kelly_pick_id": "kellylab-pick-v1:" + "a" * 64,
                    "home_team": "Home",
                    "away_team": "Away",
                    "competition_name": "League",
                    "market": "BTTS",
                    "selection": "YES",
                    "odds": 2.0,
                    "bookmaker": "Bet365",
                    "model_probability": 0.55,
                    "kelly_probability": 0.55,
                    "calibration_gap": 0.0,
                    "raw_kelly_fraction": 0.10,
                    "applied_kelly_fraction": 0.01,
                    "bankroll_before_minor": 3_000_000,
                    "stake_minor": 30_000,
                    "flat_stake_minor": 30_000,
                    "decision": "BET",
                    "outcome": "PENDING",
                    "kelly_pnl_minor": None,
                    "flat_pnl_minor": None,
                    "source_decision_at": NOW,
                    "kickoff_at": NOW + timedelta(hours=2),
                    "regulation_home_goals": None,
                    "regulation_away_goals": None,
                    "source_payload": {"late_materialization": False},
                }
            ],
        }


def test_dashboard_exposes_30k_starting_bankroll_and_shadow_contract() -> None:
    html = KellyLabDashboardService(FakeRepository(), clock=lambda: NOW).render_html()

    assert "KellyLab" in html
    assert "30 000.00 RSD" in html
    assert "Quarter Kelly" in html
    assert "1% hard cap" in html
    assert "300.00 RSD" in html
    assert "Home – Away" in html
