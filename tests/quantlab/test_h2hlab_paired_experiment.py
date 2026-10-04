from h2h.quantlab.h2h_lab.experiment import (
    arm_relation,
    canonical_arm,
    probability_trials,
    settle_experiment,
    should_freeze,
)


def _candidate(
    *,
    market: str = "BTTS",
    selection: str = "YES",
    bookmaker: int = 8,
    odds: float = 2.0,
    dc_probability: float = 0.54,
    composite_probability: float = 0.62,
    market_probability: float = 0.50,
    common_reason=None,
):
    dc_edge = dc_probability - market_probability
    dc_ev = dc_probability * odds - 1.0
    h2h_edge = composite_probability - market_probability
    h2h_ev = composite_probability * odds - 1.0

    def reason(edge, ev):
        if common_reason is not None:
            return common_reason
        if edge < 0.03:
            return "EDGE_BELOW_MINIMUM"
        if ev < 0.03:
            return "EV_BELOW_MINIMUM"
        return None

    return {
        "pair": {
            "bookmaker_id": bookmaker,
            "bookmaker_name": "Book",
            "provider_bet_id": 8 if market == "BTTS" else 5,
            "provider_bet_name": market,
            "market_key": market,
            "line": None if market == "BTTS" else 2.5,
            "captured_at": __import__("datetime").datetime(2026, 10, 4, tzinfo=__import__("datetime").UTC),
        },
        "selection": selection,
        "selected": {"market_observation_id": f"s-{market}-{selection}-{bookmaker}"},
        "companion": {"market_observation_id": f"c-{market}-{selection}-{bookmaker}"},
        "odds": odds,
        "companion_odds": 1.8,
        "market_probability": market_probability,
        "dc_probability": dc_probability,
        "h2h_probability": composite_probability,
        "model_probability": composite_probability,
        "dc_edge": dc_edge,
        "dc_expected_value": dc_ev,
        "edge": h2h_edge,
        "expected_value": h2h_ev,
        "common_reason": common_reason,
        "dc_reason": reason(dc_edge, dc_ev),
        "reason": reason(h2h_edge, h2h_ev),
        "agreement": "CONFIRM",
    }


def test_paired_arms_can_create_h2h_only_bet() -> None:
    rows = [_candidate()]
    assert should_freeze(rows)

    dc = canonical_arm(
        rows,
        arm="DC_ONLY",
        reason_key="dc_reason",
        probability_key="dc_probability",
        edge_key="dc_edge",
        ev_key="dc_expected_value",
    )
    h2h = canonical_arm(
        rows,
        arm="DC_H2H",
        reason_key="reason",
        probability_key="model_probability",
        edge_key="edge",
        ev_key="expected_value",
    )

    assert dc["decision"] == "NO_BET"
    assert h2h["decision"] == "BET"
    assert arm_relation(dc, h2h) == "H2H_ONLY"


def test_experiment_does_not_freeze_on_execution_invalid_quotes() -> None:
    assert not should_freeze([_candidate(common_reason="STALE_QUOTE")])


def test_probability_trials_are_bookmaker_independent() -> None:
    rows = [
        _candidate(bookmaker=11),
        _candidate(bookmaker=8),
        _candidate(market="OU_25", selection="OVER", bookmaker=8),
    ]
    trials = probability_trials(rows)
    assert [item["market_key"] for item in trials] == ["BTTS", "OU_25"]
    assert all("dc_probability" in item and "composite_probability" in item for item in trials)


def test_settlement_measures_roi_and_brier_rescue() -> None:
    row = {
        "experiment_id": "quantlab-h2h-experiment-v1:" + "a" * 64,
        "fixture_id": "api-football:1",
        "provider_status": "FT",
        "home_goals": 2,
        "away_goals": 1,
        "dc_arm": {"decision": "NO_BET"},
        "h2h_arm": {
            "decision": "BET",
            "market_key": "BTTS",
            "selection": "YES",
            "odds": 2.0,
        },
        "probability_trials": [
            {
                "market_key": "BTTS",
                "selection": "YES",
                "dc_probability": 0.55,
                "composite_probability": 0.70,
                "h2h_probability": 0.80,
                "agreement": "CONFIRM",
            }
        ],
    }
    settled = settle_experiment(row)
    assert settled is not None
    assert settled.dc_outcome == "NO_BET"
    assert settled.h2h_outcome == "WIN"
    assert settled.h2h_pnl_minor == 10_000
    assert settled.outcome_regime == "H2H_RESCUE"
    assert settled.brier_uplift is not None and settled.brier_uplift > 0
