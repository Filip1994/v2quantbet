"""Paired H2HLab experiment: plain DC vs DC+H2H on identical frozen evidence."""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum
from typing import Any

EXPERIMENT_VERSION = "H2HLAB_PAIRED_DC_VS_H2H_V1"
FLAT_STAKE_MINOR = 10_000
PRIMARY_TRIAL_SELECTION = {"OU_25": "OVER", "BTTS": "YES"}


def _eligible(item: dict[str, Any], reason_key: str) -> bool:
    return item.get(reason_key) is None


def _rank(item: dict[str, Any], *, ev_key: str, edge_key: str, probability_key: str) -> tuple[float, float, float, float, int]:
    return (
        float(item[ev_key]),
        float(item[edge_key]),
        float(item[probability_key]),
        float(item["odds"]),
        -int(item["pair"]["bookmaker_id"]),
    )


def canonical_arm(
    evaluated: list[dict[str, Any]],
    *,
    arm: str,
    reason_key: str,
    probability_key: str,
    edge_key: str,
    ev_key: str,
) -> dict[str, Any]:
    eligible = [item for item in evaluated if _eligible(item, reason_key)]
    canonical = max(
        eligible,
        key=lambda item: _rank(
            item,
            ev_key=ev_key,
            edge_key=edge_key,
            probability_key=probability_key,
        ),
        default=None,
    )
    if canonical is None:
        reasons = sorted({str(item.get(reason_key) or "NO_ELIGIBLE_CANDIDATE") for item in evaluated})
        return {
            "arm": arm,
            "decision": "NO_BET",
            "reason": reasons[0] if len(reasons) == 1 else "NO_ELIGIBLE_CANDIDATE",
        }
    pair = canonical["pair"]
    selected = canonical["selected"]
    companion = canonical["companion"]
    return {
        "arm": arm,
        "decision": "BET",
        "reason": "CANONICAL_VALUE_BET",
        "bookmaker_id": int(pair["bookmaker_id"]),
        "bookmaker_name": str(pair["bookmaker_name"]),
        "provider_bet_id": int(pair["provider_bet_id"]),
        "provider_bet_name": str(pair["provider_bet_name"]),
        "market_key": str(pair["market_key"]),
        "selection": str(canonical["selection"]),
        "line": None if pair.get("line") is None else float(pair["line"]),
        "selected_observation_id": str(selected["market_observation_id"]),
        "companion_observation_id": str(companion["market_observation_id"]),
        "quote_observed_at": pair["captured_at"].isoformat(),
        "odds": float(canonical["odds"]),
        "companion_odds": float(canonical["companion_odds"]),
        "market_probability": float(canonical["market_probability"]),
        "model_probability": float(canonical[probability_key]),
        "edge": float(canonical[edge_key]),
        "expected_value": float(canonical[ev_key]),
        "agreement": str(canonical["agreement"]),
        "h2h_probability": float(canonical["h2h_probability"]),
        "dc_probability": float(canonical["dc_probability"]),
    }


def arm_relation(dc_arm: dict[str, Any], h2h_arm: dict[str, Any]) -> str:
    dc_bet = dc_arm.get("decision") == "BET"
    h2h_bet = h2h_arm.get("decision") == "BET"
    if not dc_bet and not h2h_bet:
        return "BOTH_NO_BET"
    if dc_bet and not h2h_bet:
        return "DC_ONLY"
    if h2h_bet and not dc_bet:
        return "H2H_ONLY"
    if dc_arm["market_key"] != h2h_arm["market_key"]:
        return "DIFFERENT_MARKET"
    if dc_arm["selection"] != h2h_arm["selection"]:
        return "FLIP"
    if dc_arm["bookmaker_id"] != h2h_arm["bookmaker_id"] or dc_arm["odds"] != h2h_arm["odds"]:
        return "SAME_SIDE_DIFFERENT_PRICE"
    return "SAME_BET"


def probability_trials(evaluated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One binary probability trial per market, independent of bookmaker."""
    by_market: dict[str, dict[str, Any]] = {}
    for item in evaluated:
        market = str(item["pair"]["market_key"])
        if item["selection"] != PRIMARY_TRIAL_SELECTION.get(market):
            continue
        current = by_market.get(market)
        if current is None or int(item["pair"]["bookmaker_id"]) < int(current["pair"]["bookmaker_id"]):
            by_market[market] = item
    return [
        {
            "market_key": market,
            "selection": str(item["selection"]),
            "dc_probability": float(item["dc_probability"]),
            "h2h_probability": float(item["h2h_probability"]),
            "composite_probability": float(item["model_probability"]),
            "agreement": str(item["agreement"]),
        }
        for market, item in sorted(by_market.items())
    ]


def should_freeze(evaluated: list[dict[str, Any]]) -> bool:
    """Freeze only when at least one quote is execution-valid before model edge/EV gates."""
    return any(item.get("common_reason") is None for item in evaluated)


@dataclass(frozen=True, slots=True)
class ExperimentSettlement:
    experiment_id: str
    fixture_id: str
    provider_status: str
    home_goals: int | None
    away_goals: int | None
    dc_outcome: str
    h2h_outcome: str
    dc_pnl_minor: int
    h2h_pnl_minor: int
    outcome_regime: str
    dc_brier_mean: float | None
    h2h_brier_mean: float | None
    brier_uplift: float | None
    probability_trials: list[dict[str, Any]]


def _event(market: str, selection: str, home: int, away: int) -> bool:
    if market == "OU_25":
        over = home + away > 2.5
        return over if selection == "OVER" else not over
    if market == "BTTS":
        yes = home > 0 and away > 0
        return yes if selection == "YES" else not yes
    raise ValueError(f"unsupported experiment market {market!r}")


def _settle_arm(arm: dict[str, Any], *, status: str, home: int | None, away: int | None) -> tuple[str, int]:
    if arm.get("decision") != "BET":
        return "NO_BET", 0
    if status in {"CANC", "ABD", "AWD", "WO"}:
        return "VOID", 0
    if home is None or away is None:
        raise ValueError("played experiment requires final goals")
    won = _event(str(arm["market_key"]), str(arm["selection"]), home, away)
    if won:
        return "WIN", round(FLAT_STAKE_MINOR * (float(arm["odds"]) - 1.0))
    return "LOSS", -FLAT_STAKE_MINOR


def _regime(dc_outcome: str, h2h_outcome: str, dc_pnl: int, h2h_pnl: int) -> str:
    if dc_outcome == "NO_BET" and h2h_outcome == "NO_BET":
        return "BOTH_NO_BET"
    if dc_outcome == "NO_BET":
        return "H2H_RESCUE" if h2h_pnl > 0 else "H2H_HARM"
    if h2h_outcome == "NO_BET":
        return "H2H_RESCUE_FILTER" if dc_pnl < 0 else "H2H_HARM_FILTER"
    if h2h_pnl > dc_pnl:
        return "H2H_OUTPERFORM"
    if h2h_pnl < dc_pnl:
        return "DC_OUTPERFORM"
    return "TIE"


def settle_experiment(row: dict[str, Any]) -> ExperimentSettlement | None:
    status = str(row.get("provider_status") or "")
    if status not in {"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO"}:
        return None
    home = row.get("home_goals")
    away = row.get("away_goals")
    if status in {"FT", "AET", "PEN"} and (not isinstance(home, int) or not isinstance(away, int)):
        return None
    if status in {"CANC", "ABD", "AWD", "WO"}:
        home = away = None

    dc_arm = dict(row["dc_arm"])
    h2h_arm = dict(row["h2h_arm"])
    dc_outcome, dc_pnl = _settle_arm(dc_arm, status=status, home=home, away=away)
    h2h_outcome, h2h_pnl = _settle_arm(h2h_arm, status=status, home=home, away=away)

    scored: list[dict[str, Any]] = []
    dc_scores: list[float] = []
    h2h_scores: list[float] = []
    if home is not None and away is not None:
        for trial in row.get("probability_trials") or []:
            item = dict(trial)
            target = 1.0 if _event(str(item["market_key"]), str(item["selection"]), home, away) else 0.0
            dc_score = (float(item["dc_probability"]) - target) ** 2
            h2h_score = (float(item["composite_probability"]) - target) ** 2
            item.update({"actual": int(target), "dc_brier": dc_score, "h2h_brier": h2h_score})
            scored.append(item)
            dc_scores.append(dc_score)
            h2h_scores.append(h2h_score)

    dc_brier = fsum(dc_scores) / len(dc_scores) if dc_scores else None
    h2h_brier = fsum(h2h_scores) / len(h2h_scores) if h2h_scores else None
    uplift = None if dc_brier is None or h2h_brier is None else dc_brier - h2h_brier
    return ExperimentSettlement(
        experiment_id=str(row["experiment_id"]),
        fixture_id=str(row["fixture_id"]),
        provider_status=status,
        home_goals=home,
        away_goals=away,
        dc_outcome=dc_outcome,
        h2h_outcome=h2h_outcome,
        dc_pnl_minor=dc_pnl,
        h2h_pnl_minor=h2h_pnl,
        outcome_regime=_regime(dc_outcome, h2h_outcome, dc_pnl, h2h_pnl),
        dc_brier_mean=dc_brier,
        h2h_brier_mean=h2h_brier,
        brier_uplift=uplift,
        probability_trials=scored,
    )
