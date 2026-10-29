from __future__ import annotations

import pytest

from h2h.roi_kelly import calculate_roi_kelly


def plan(
    *,
    wins: int,
    losses: int,
    historical_unit_pnl: float,
    odds: float = 1.875,
    verified: bool = True,
):
    return calculate_roi_kelly(
        bucket_id="CORNER_CUBE_OVER_O175_200_P55_60_EV05_10_G0_1",
        wins=wins,
        losses=losses,
        historical_unit_pnl=historical_unit_pnl,
        quote_odds=odds,
        bankroll_minor=3_000_000,
        verified_one_xbet=verified,
    )


def test_under_31_settled_is_not_bet_even_with_high_roi():
    p = plan(wins=15, losses=3, historical_unit_pnl=15 * 0.7 - 3)
    assert p.graded_n == 18
    assert p.reason == "INSUFFICIENT_SAME_BOOKMAKER_N"
    assert p.stake_minor == 0
    assert p.decision == "NO_BET"


def test_small_observed_positive_roi_does_not_force_kelly_bet():
    p = plan(wins=44, losses=32, historical_unit_pnl=44 * 0.875 - 32)
    assert p.graded_n == 76
    assert p.historical_roi_pct > 0
    assert p.conservative_probability < p.break_even_probability
    assert p.reason == "NO_CONSERVATIVE_EDGE"
    assert p.stake_minor == 0


def test_strong_and_large_1xbet_cohort_gets_quarter_kelly_with_cap():
    p = plan(wins=230, losses=70, historical_unit_pnl=230 * 0.875 - 70)
    assert p.reason == "PASS"
    assert p.conservative_probability > p.break_even_probability
    assert p.applied_fraction == pytest.approx(0.01)
    assert p.stake_minor == 30_000
    assert p.decision == "BET"


def test_wrong_bookmaker_blocks_even_strong_cohort():
    p = plan(
        wins=230, losses=70, historical_unit_pnl=230 * 0.875 - 70,
        verified=False,
    )
    assert p.reason == "NOT_VERIFIED_1XBET"
    assert p.stake_minor == 0


def test_negative_realized_roi_blocks_promotion():
    p = plan(wins=100, losses=100, historical_unit_pnl=-10.0)
    assert p.reason == "NON_POSITIVE_HISTORICAL_ROI"
    assert p.stake_minor == 0


def test_no_signal_is_safe():
    p = plan(wins=0, losses=0, historical_unit_pnl=0.0)
    assert p.reason == "INSUFFICIENT_SAME_BOOKMAKER_N"
    assert p.stake_minor == 0


@pytest.mark.parametrize("wins,losses,unit_pnl,odds", [
    (-1, 40, 0.0, 1.8),
    (40, -1, 0.0, 1.8),
    (40, 1, float("nan"), 1.8),
    (40, 1, 0.0, 1.0),
    (0, 4, -5.0, 1.8),
])
def test_invalid_evidence_is_rejected(wins, losses, unit_pnl, odds):
    with pytest.raises(ValueError):
        plan(wins=wins, losses=losses,
             historical_unit_pnl=unit_pnl, odds=odds)


def test_report_filters_non_1xbet_evidence_and_uses_existing_cube():
    from scripts.roi_kelly_corner_report import make_report

    base = {
        "market_key": "TOTAL_CORNERS",
        "selection": "OVER",
        "odds": 1.875,
        "model_probability": 0.575,
        "expected_value": 0.078125,
        "line": 8.5,
        "expected_total_corners": 9.0,
        "country": "Serbia",
        "competition_name": "Super Liga",
        "league_id": 286,
        "home_team": "Test Home",
        "away_team": "Test Away",
        "outcome": "WIN",
        "stake_minor": 10_000,
        "pnl_minor": 8750,
        "bookmaker_id": 11,
        "bookmaker_name": "1xBet",
    }
    other = {**base, "bookmaker_id": 8, "bookmaker_name": "bet365"}
    result = make_report((base, other), bankroll_minor=3_000_000)
    bucket = next(r for r in result["buckets"] if "OVER_O175_200" in r["bucket_id"])
    assert bucket["roi_kelly_example"]["graded_n"] == 1
    assert bucket["roi_kelly_example"]["wins"] == 1
    assert result["excluded_rows"]["other_bookmaker"] == 1
    assert bucket["roi_kelly_example"]["stake_minor"] == 0
