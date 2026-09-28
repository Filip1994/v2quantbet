"""GoalLab canonical pick selection and settlement semantics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from h2h.domain.fixture_result import ApiFootballSettlementResultNormalizer


PICK_POLICY_VERSION = "GOALLAB_DC_PLUS_PICK_POLICY_V1"
SETTLEMENT_RULE_VERSION = "GOALLAB_SETTLEMENT_V1"
FLAT_STAKE_MINOR = 10_000

GOAL_RESULT_INITIAL_DELAY_SECONDS = 6_300
GOAL_RESULT_REFRESH_SECONDS = 900
GOAL_RESULT_POSTPONED_REFRESH_SECONDS = 21_600
GOAL_RESULT_FINALITY_DELAY_SECONDS = 900


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



def stable_goal_result_evidence(
    row: dict[str, Any],
    *,
    finality_delay_seconds: int = GOAL_RESULT_FINALITY_DELAY_SECONDS,
) -> dict[str, Any] | None:
    """Confirm one GoalLab result from two matching QuantLab-owned provider snapshots."""
    if finality_delay_seconds <= 0:
        raise ValueError("finality_delay_seconds must be positive")

    latest_payload = row.get("latest_result_raw_payload")
    previous_payload = row.get("previous_result_raw_payload")
    latest_captured = row.get("latest_result_captured_at")
    previous_captured = row.get("previous_result_captured_at")
    if (
        latest_payload is None
        or previous_payload is None
        or latest_captured is None
        or previous_captured is None
    ):
        return None

    if isinstance(latest_payload, str):
        latest_payload = json.loads(latest_payload)
    if isinstance(previous_payload, str):
        previous_payload = json.loads(previous_payload)
    if not isinstance(latest_payload, dict) or not isinstance(previous_payload, dict):
        return None

    if latest_captured < previous_captured:
        raise ValueError("GoalLab result observations are out of chronological order")
    elapsed = (latest_captured - previous_captured).total_seconds()
    if elapsed < finality_delay_seconds:
        return None

    fixture_id = str(row["fixture_id"])
    normalizer = ApiFootballSettlementResultNormalizer()
    latest = normalizer.normalize(
        latest_payload,
        fixture_id=fixture_id,
        acquired_at=latest_captured,
    )
    previous = normalizer.normalize(
        previous_payload,
        fixture_id=fixture_id,
        acquired_at=previous_captured,
    )
    if not latest.is_terminal_candidate or not previous.is_terminal_candidate:
        return None
    if latest.settlement_fingerprint != previous.settlement_fingerprint:
        return None

    return {
        "result_observation_id": str(row["latest_result_observation_id"]),
        "provider_status": latest.provider_status,
        "result_classification": latest.classification.value,
        "regulation_home_goals": latest.regulation_goals[0],
        "regulation_away_goals": latest.regulation_goals[1],
        "result_confirmation_count": 2,
        "result_first_confirmed_at": previous_captured,
        "result_confirmed_at": latest_captured,
        "result_settlement_fingerprint": latest.settlement_fingerprint,
    }

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
