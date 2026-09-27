"""1xBet-only CardLab event parsing and settlement."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from h2h.quantlab.card_lab.settlement_contract import (
    API_FOOTBALL_CARDS_OVER_UNDER_BET_ID,
)


SETTLEMENT_RULE_VERSION = "CARDLAB_1XBET_TOTAL_CARDS_SETTLEMENT_V1"


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _identifier(prefix: str, payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return prefix + sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class CardEventObservation:
    card_event_observation_id: str
    fixture_id: str
    provider_fixture_id: int
    total_cards_1xbet: int
    qualifying_event_count: int
    available_at: datetime
    settlement_rule_version: str
    event_payload: tuple[dict[str, Any], ...]
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CardShadowSettlement:
    shadow_bet_id: str
    fixture_id: str
    fixture_observation_id: str
    card_event_observation_id: str | None
    outcome: str
    pnl_minor: int
    settled_at: datetime
    settlement_rule_version: str
    result_detail: dict[str, Any]


def parse_1xbet_card_events(
    payload: Mapping[str, Any],
    *,
    fixture_id: str,
    provider_fixture_id: int,
    captured_at: datetime,
) -> CardEventObservation:
    """Normalize API-Football card events into the 1xBet Cards Over/Under count.

    API-Football exposes card timeline details as Yellow Card, Red Card and
    Yellow-Red Card. 1xBet Cards Over/Under counts regular time including stoppage
    time, excludes extra time, and caps a player's contribution at two cards.
    Requiring a provider player ID also prevents staff/unknown card events from
    entering the settlement count.
    """
    captured = _utc(captured_at, "captured_at")
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")
    response = payload.get("response")
    if not isinstance(response, list):
        raise TypeError("events response must contain a list")

    normalized: list[dict[str, Any]] = []
    per_player: dict[int, int] = defaultdict(int)
    for index, record in enumerate(response):
        if not isinstance(record, Mapping):
            continue
        if str(record.get("type") or "").strip().casefold() != "card":
            continue

        detail = str(record.get("detail") or "").strip()
        detail_key = detail.casefold().replace("_", "-")
        if not any(
            token in detail_key
            for token in ("yellow card", "red card", "yellow-red card", "second yellow")
        ):
            continue

        time = record.get("time")
        if not isinstance(time, Mapping):
            continue
        elapsed = time.get("elapsed")
        extra = time.get("extra")
        if isinstance(elapsed, bool) or not isinstance(elapsed, int):
            continue
        # API-Football represents extra time periods above minute 90. Stoppage
        # time remains elapsed=45/90 with the extra component populated.
        if elapsed < 0 or elapsed > 90:
            continue

        player = record.get("player")
        if not isinstance(player, Mapping):
            continue
        player_id = player.get("id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id <= 0:
            continue

        per_player[player_id] += 1
        normalized.append(
            {
                "provider_order": index,
                "elapsed": elapsed,
                "extra": extra if isinstance(extra, int) else None,
                "player_id": player_id,
                "player_name": str(player.get("name") or "").strip() or None,
                "team_id": (
                    int(record["team"]["id"])
                    if isinstance(record.get("team"), Mapping)
                    and isinstance(record["team"].get("id"), int)
                    else None
                ),
                "detail": detail,
            }
        )

    total_cards = sum(min(count, 2) for count in per_player.values())
    identity = {
        "fixture_id": fixture_id,
        "provider_fixture_id": provider_fixture_id,
        "available_at": captured.isoformat(),
        "settlement_rule_version": SETTLEMENT_RULE_VERSION,
        "events": normalized,
    }
    return CardEventObservation(
        card_event_observation_id=_identifier("quantlab-card-events-v1:", identity),
        fixture_id=fixture_id,
        provider_fixture_id=provider_fixture_id,
        total_cards_1xbet=total_cards,
        qualifying_event_count=len(normalized),
        available_at=captured,
        settlement_rule_version=SETTLEMENT_RULE_VERSION,
        event_payload=tuple(normalized),
        raw_payload=dict(payload),
    )


def settle_card_shadow_bet(
    row: Mapping[str, Any],
    *,
    settled_at: datetime,
) -> CardShadowSettlement | None:
    classification = str(row.get("result_classification") or "")
    if classification not in {"PLAYED_SETTLEABLE", "NON_PLAYED_VOIDABLE"}:
        return None

    settled = _utc(settled_at, "settled_at")
    shadow_bet_id = str(row["shadow_bet_id"])
    fixture_id = str(row["fixture_id"])
    fixture_observation_id = str(row["fixture_observation_id"])
    stake_minor = int(row["stake_minor"])

    if classification == "NON_PLAYED_VOIDABLE":
        return CardShadowSettlement(
            shadow_bet_id=shadow_bet_id,
            fixture_id=fixture_id,
            fixture_observation_id=fixture_observation_id,
            card_event_observation_id=None,
            outcome="VOID",
            pnl_minor=0,
            settled_at=settled,
            settlement_rule_version=SETTLEMENT_RULE_VERSION,
            result_detail={
                "settlement_rule_version": SETTLEMENT_RULE_VERSION,
                "result_classification": classification,
                "provider_status": row.get("provider_status"),
                "rule": "non-played terminal fixture voids CardLab shadow bet",
            },
        )

    if str(row.get("market_key") or "") != "TOTAL_CARDS":
        return None
    if int(row.get("bookmaker_id") or 0) != 11:
        return None
    if int(row.get("provider_bet_id") or 0) != API_FOOTBALL_CARDS_OVER_UNDER_BET_ID:
        return None
    selection = str(row.get("selection") or "").upper()
    if selection not in {"OVER", "UNDER"}:
        return None

    line = float(row["line"])
    odds = float(row["odds"])
    if not isfinite(line) or not isfinite(odds) or odds <= 1:
        return None
    card_observation_id = row.get("card_event_observation_id")
    total_cards = row.get("total_cards_1xbet")
    if card_observation_id is None or total_cards is None:
        return None
    total = int(total_cards)

    if selection == "OVER":
        outcome = "WIN" if total > line else "LOSS"
    else:
        outcome = "WIN" if total < line else "LOSS"
    pnl_minor = round(stake_minor * (odds - 1.0)) if outcome == "WIN" else -stake_minor

    return CardShadowSettlement(
        shadow_bet_id=shadow_bet_id,
        fixture_id=fixture_id,
        fixture_observation_id=fixture_observation_id,
        card_event_observation_id=str(card_observation_id),
        outcome=outcome,
        pnl_minor=pnl_minor,
        settled_at=settled,
        settlement_rule_version=SETTLEMENT_RULE_VERSION,
        result_detail={
            "settlement_rule_version": SETTLEMENT_RULE_VERSION,
            "result_classification": classification,
            "provider_status": row.get("provider_status"),
            "card_event_observation_id": str(card_observation_id),
            "total_cards_1xbet": total,
            "selection": selection,
            "line": line,
            "odds": odds,
            "rule": (
                "1xBet Cards Over/Under: regular time including stoppage; extra time excluded; "
                "player card events only; max two cards per player"
            ),
        },
    )
