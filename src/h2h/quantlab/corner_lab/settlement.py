"""Settlement rules for CornerLab full-match total-corner shadow bets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


SETTLEMENT_RULE_VERSION = "CORNERLAB_TOTAL_CORNERS_HALF_LINE_SETTLEMENT_V1"


@dataclass(frozen=True, slots=True)
class CornerShadowSettlement:
    shadow_bet_id: str
    fixture_id: str
    result_observation_id: str
    statistics_observation_id: str | None
    outcome: str
    pnl_minor: int
    settled_at: datetime
    settlement_rule_version: str
    result_detail: dict[str, Any]


def settle_corner_shadow_bet(
    row: dict[str, Any],
    *,
    settled_at: datetime,
) -> CornerShadowSettlement | None:
    """Settle one CornerLab shadow pick from terminal result + corner statistics."""
    classification = str(row.get("result_classification") or "")
    if classification not in {"PLAYED_SETTLEABLE", "NON_PLAYED_VOIDABLE"}:
        return None

    shadow_bet_id = str(row["shadow_bet_id"])
    fixture_id = str(row["fixture_id"])
    result_observation_id = str(row["result_observation_id"])
    statistics_observation_id = (
        None
        if row.get("statistics_observation_id") is None
        else str(row["statistics_observation_id"])
    )
    stake_minor = int(row["stake_minor"])

    if classification == "NON_PLAYED_VOIDABLE":
        return CornerShadowSettlement(
            shadow_bet_id=shadow_bet_id,
            fixture_id=fixture_id,
            result_observation_id=result_observation_id,
            statistics_observation_id=None,
            outcome="VOID",
            pnl_minor=0,
            settled_at=settled_at,
            settlement_rule_version=SETTLEMENT_RULE_VERSION,
            result_detail={
                "settlement_rule_version": SETTLEMENT_RULE_VERSION,
                "result_observation_id": result_observation_id,
                "result_classification": classification,
                "provider_status": row.get("provider_status"),
                "rule": "non-played terminal fixture voids CornerLab shadow bet",
            },
        )

    home_raw = row.get("home_corner_kicks")
    away_raw = row.get("away_corner_kicks")
    if home_raw is None or away_raw is None:
        return None

    market_key = str(row.get("market_key") or "")
    selection = str(row.get("selection") or "").upper()
    line_raw = row.get("line")
    if market_key != "TOTAL_CORNERS" or selection not in {"OVER", "UNDER"} or line_raw is None:
        raise ValueError("unsupported CornerLab settlement market")

    line = Decimal(str(line_raw))
    if (line * Decimal(2)) % Decimal(2) != Decimal(1):
        raise ValueError("CornerLab settlement requires a half-line")

    home_corners = int(home_raw)
    away_corners = int(away_raw)
    actual_total = home_corners + away_corners
    won = Decimal(actual_total) > line if selection == "OVER" else Decimal(actual_total) < line
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

    return CornerShadowSettlement(
        shadow_bet_id=shadow_bet_id,
        fixture_id=fixture_id,
        result_observation_id=result_observation_id,
        statistics_observation_id=statistics_observation_id,
        outcome=outcome,
        pnl_minor=pnl_minor,
        settled_at=settled_at,
        settlement_rule_version=SETTLEMENT_RULE_VERSION,
        result_detail={
            "settlement_rule_version": SETTLEMENT_RULE_VERSION,
            "result_observation_id": result_observation_id,
            "result_classification": classification,
            "provider_status": row.get("provider_status"),
            "statistics_observation_id": statistics_observation_id,
            "statistics_available_at": row.get("statistics_available_at"),
            "home_corner_kicks": home_corners,
            "away_corner_kicks": away_corners,
            "actual_total_corners": actual_total,
            "market_key": market_key,
            "selection": selection,
            "line": float(line),
            "odds": float(row["odds"]),
            "stake_minor": stake_minor,
        },
    )
