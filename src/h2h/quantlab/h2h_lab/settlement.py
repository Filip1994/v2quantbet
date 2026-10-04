"""H2HLab V1 settlement for O/U 2.5 and BTTS shadow picks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

SETTLEMENT_RULE_VERSION = "H2HLAB_GOAL_MARKETS_SETTLEMENT_V1"

@dataclass(frozen=True, slots=True)
class H2HSettlement:
    shadow_bet_id: str
    fixture_id: str
    outcome: str
    pnl_minor: int
    settled_at: datetime
    result_detail: dict[str, Any]


def settle_h2h_shadow_bet(row: dict[str, Any], *, settled_at: datetime) -> H2HSettlement | None:
    status = str(row.get("provider_status") or "")
    if status not in {"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO"}:
        return None
    when = settled_at.astimezone(UTC)
    if status in {"CANC", "ABD", "AWD", "WO"}:
        outcome = "VOID"
        pnl = 0
        home = away = None
    else:
        home, away = row.get("home_goals"), row.get("away_goals")
        if not isinstance(home, int) or not isinstance(away, int):
            return None
        market, selection = str(row["market_key"]), str(row["selection"])
        if market == "OU_25":
            win = (home + away > 2.5) if selection == "OVER" else (home + away < 2.5)
        elif market == "BTTS":
            yes = home > 0 and away > 0
            win = yes if selection == "YES" else not yes
        else:
            return None
        outcome = "WIN" if win else "LOSS"
        stake = int(row["stake_minor"])
        pnl = round(stake * (float(row["odds"]) - 1.0)) if win else -stake
    return H2HSettlement(
        shadow_bet_id=str(row["shadow_bet_id"]), fixture_id=str(row["fixture_id"]),
        outcome=outcome, pnl_minor=pnl, settled_at=when,
        result_detail={
            "provider_status": status, "home_goals": home, "away_goals": away,
            "settlement_rule_version": SETTLEMENT_RULE_VERSION,
        },
    )
