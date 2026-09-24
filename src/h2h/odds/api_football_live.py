"""Strict normalization for API-Football live odds used only as a market-close proxy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError


API_FOOTBALL_LIVE_BET_IDENTITIES: dict[Market, tuple[int, str]] = {
    Market.OU_25: (25, "Match Goals"),
    Market.BTTS: (69, "Both Teams to Score"),
}


@dataclass(frozen=True, slots=True)
class LiveMarketQuote:
    provider_fixture_id: int
    market: Market
    selection: Selection
    odd: float
    observed_at: datetime
    live_bet_id: int
    live_bet_name: str
    source: str = "api-football-live"


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("live update must be an ISO datetime string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("live update must be timezone-aware")
    return parsed


def _normalized(value: str) -> str:
    return " ".join(value.casefold().replace("/", " ").replace("-", " ").split())


def _finite_odd(value: Any) -> float:
    if isinstance(value, bool):
        raise TypeError("odd must be numeric")
    try:
        odd = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("odd must be numeric") from exc
    if not isfinite(odd) or odd <= 1:
        raise ValueError("odd must be finite and greater than one")
    return odd


def _selection(
    market: Market, value: Mapping[str, Any]
) -> Selection | None:
    raw = value.get("value")
    if not isinstance(raw, str):
        return None
    token = raw.strip().upper()
    if market is Market.BTTS:
        return {"YES": Selection.YES, "NO": Selection.NO}.get(token)
    if token not in {"OVER", "UNDER"}:
        return None
    handicap = value.get("handicap")
    try:
        line = float(handicap)
    except (TypeError, ValueError):
        return None
    if line != 2.5:
        return None
    return Selection.OVER if token == "OVER" else Selection.UNDER


def parse_api_football_live_quotes(
    response: Mapping[str, Any], *, fixture_id: int
) -> tuple[LiveMarketQuote, ...]:
    """Return only exact OU2.5/BTTS live values for one requested fixture.

    API-Football live odds are not bookmaker-specific. These observations must
    never be inserted into a bookmaker quote series or presented as same-book close.
    """
    if not isinstance(response, Mapping):
        raise TypeError("API-Football live odds response must be an object")
    errors = response.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned live odds errors: {errors}")
    records = response.get("response", [])
    if not isinstance(records, list):
        raise TypeError("API-Football live odds response must contain a list")

    result: list[LiveMarketQuote] = []
    for index, record in enumerate(records):
        try:
            if not isinstance(record, Mapping):
                raise TypeError("response record must be a mapping")
            fixture = record.get("fixture")
            if not isinstance(fixture, Mapping) or fixture.get("id") != fixture_id:
                raise ValueError("live fixture.id does not match requested fixture")
            status = record.get("status")
            if isinstance(status, Mapping) and bool(status.get("blocked")):
                continue
            observed_at = _parse_datetime(record.get("update"))
            odds = record.get("odds", [])
            if not isinstance(odds, list):
                continue

            for market, (expected_id, expected_name) in API_FOOTBALL_LIVE_BET_IDENTITIES.items():
                matches = [
                    bet
                    for bet in odds
                    if isinstance(bet, Mapping) and bet.get("id") == expected_id
                ]
                if not matches:
                    continue
                if len(matches) != 1:
                    raise ValueError(f"duplicate live bet id {expected_id}")
                bet = matches[0]
                name = bet.get("name")
                if not isinstance(name, str) or _normalized(name) != _normalized(expected_name):
                    raise ValueError(
                        f"live bet id/name mismatch: id={expected_id}, name={name!r}"
                    )
                values = bet.get("values", [])
                if not isinstance(values, list):
                    continue

                candidates: dict[Selection, list[tuple[bool, LiveMarketQuote]]] = {}
                for value in values:
                    if not isinstance(value, Mapping) or bool(value.get("suspended")):
                        continue
                    selection = _selection(market, value)
                    if selection is None:
                        continue
                    quote = LiveMarketQuote(
                        provider_fixture_id=fixture_id,
                        market=market,
                        selection=selection,
                        odd=_finite_odd(value.get("odd")),
                        observed_at=observed_at,
                        live_bet_id=expected_id,
                        live_bet_name=expected_name,
                    )
                    candidates.setdefault(selection, []).append(
                        (value.get("main") is True, quote)
                    )

                for selection_candidates in candidates.values():
                    if len(selection_candidates) == 1:
                        result.append(selection_candidates[0][1])
                        continue
                    primary = [quote for is_main, quote in selection_candidates if is_main]
                    if len(primary) != 1:
                        raise ValueError(
                            f"ambiguous live values for bet id {expected_id}"
                        )
                    result.append(primary[0])
        except (TypeError, ValueError) as exc:
            raise QuoteNormalizationError(
                f"invalid API-Football live odds record at index {index}: {exc}"
            ) from exc
    return tuple(result)
