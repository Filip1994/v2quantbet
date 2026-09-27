"""GoalLab canonical pick selection and settlement semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


PICK_POLICY_VERSION = "GOALLAB_DC_PLUS_PICK_POLICY_V1"
SETTLEMENT_RULE_VERSION = "GOALLAB_SETTLEMENT_V1"
FLAT_STAKE_MINOR = 10_000


@dataclass(frozen=True, slots=True)
class GoalCanonicalPick:
    fixture_id: str
    source_decision_id: str
    decision_at: datetime
    kickoff_at: datetime
    pick_policy_version: str
    model_name: str
    model_version: str
    bookmaker_id: int
    bookmaker_name: str
    provider_bet_id: int
    provider_bet_name: str
    market_key: str
    selection: str
    line: float | None
    selected_observation_id: str
    companion_observation_id: str
    quote_observed_at: datetime
    odds: float
    companion_odds: float
    market_probability: float
    model_probability: float
    edge: float
    expected_value: float
    expected_home_goals: float
    expected_away_goals: float
    rho: float
    stake_minor: int
    qualifying_candidate_count: int
    selection_rank_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GoalPickSettlement:
    goal_pick_id: str
    fixture_id: str
    result_observation_id: str
    result_classification: str
    regulation_home_goals: int | None
    regulation_away_goals: int | None
    outcome: str
    pnl_minor: int
    settled_at: datetime
    settlement_rule_version: str
    result_detail: dict[str, Any]


def candidate_rank(item: dict[str, Any]) -> tuple[float, float, float, float, str, str, int]:
    """Higher tuple is better; final fields make ties deterministic."""
    pair = item["pair"]
    return (
        float(item["expected_value"]),
        float(item["edge"]),
        float(item["model_probability"]),
        float(item["odds"]),
        str(pair["market_key"]),
        str(item["selection"]),
        -int(pair["bookmaker_id"]),
    )


def choose_canonical_candidate(
    candidates: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None
    return max(candidates, key=candidate_rank)


def settle_goal_pick(
    row: dict[str, Any],
    *,
    settled_at: datetime,
) -> GoalPickSettlement | None:
    """Settle one canonical GoalLab pick from stable shared result facts."""
    classification = str(row.get("result_classification") or "")
    if classification not in {"PLAYED_SETTLEABLE", "NON_PLAYED_VOIDABLE"}:
        return None

    pick_id = str(row["goal_pick_id"])
    fixture_id = str(row["fixture_id"])
    result_observation_id = str(row["result_observation_id"])
    stake_minor = int(row["stake_minor"])

    if classification == "NON_PLAYED_VOIDABLE":
        return GoalPickSettlement(
            goal_pick_id=pick_id,
            fixture_id=fixture_id,
            result_observation_id=result_observation_id,
            result_classification=classification,
            regulation_home_goals=None,
            regulation_away_goals=None,
            outcome="VOID",
            pnl_minor=0,
            settled_at=settled_at,
            settlement_rule_version=SETTLEMENT_RULE_VERSION,
            result_detail={
                "market_key": row["market_key"],
                "selection": row["selection"],
                "provider_status": row.get("provider_status"),
                "rule": "non-played terminal fixture voids GoalLab pick",
            },
        )

    home_raw = row.get("regulation_home_goals")
    away_raw = row.get("regulation_away_goals")
    if home_raw is None or away_raw is None:
        return None
    home = int(home_raw)
    away = int(away_raw)
    market_key = str(row["market_key"])
    selection = str(row["selection"])

    if market_key == "OU_25":
        condition = home + away > 2
        won = condition if selection == "OVER" else not condition
        semantic = f"regulation_total_goals={home + away}"
    elif market_key == "BTTS":
        condition = home > 0 and away > 0
        won = condition if selection == "YES" else not condition
        semantic = f"regulation_btts={condition}"
    else:
        raise ValueError(f"unsupported GoalLab settlement market {market_key!r}")

    outcome = "WIN" if won else "LOSS"
    if won:
        odds = Decimal(str(row["odds"]))
        pnl_minor = int(
            (Decimal(stake_minor) * (odds - Decimal(1))).quantize(
                Decimal(1),
                rounding=ROUND_HALF_UP,
            )
        )
    else:
        pnl_minor = -stake_minor

    return GoalPickSettlement(
        goal_pick_id=pick_id,
        fixture_id=fixture_id,
        result_observation_id=result_observation_id,
        result_classification=classification,
        regulation_home_goals=home,
        regulation_away_goals=away,
        outcome=outcome,
        pnl_minor=pnl_minor,
        settled_at=settled_at,
        settlement_rule_version=SETTLEMENT_RULE_VERSION,
        result_detail={
            "market_key": market_key,
            "selection": selection,
            "odds": float(row["odds"]),
            "stake_minor": stake_minor,
            "provider_status": row.get("provider_status"),
            "regulation_home_goals": home,
            "regulation_away_goals": away,
            "semantic": semantic,
        },
    )
