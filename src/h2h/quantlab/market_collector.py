"""All-market Bet365/1xBet parser and persistence handoff for QuantLab."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from h2h.quantlab.market_classifier import CLASSIFIER_VERSION, classify_market


BOOKMAKERS = {8: "Bet365", 11: "1xBet"}
_LINE_PATTERNS = (
    re.compile(r"^(?:over|under)\s+([+-]?\d+(?:\.\d+)?)$", re.IGNORECASE),
    re.compile(r"^(?:home|away|1|2)\s*([+-]\d+(?:\.\d+)?)$", re.IGNORECASE),
)


def _aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    if result.tzinfo is None or result.utcoffset() is None:
        return None
    return result.astimezone(UTC)


def parse_line(selection: str) -> Decimal | None:
    """Parse only deterministic line-bearing selection shapes."""
    for pattern in _LINE_PATTERNS:
        match = pattern.match(selection.strip())
        if match:
            try:
                return Decimal(match.group(1))
            except InvalidOperation:
                return None
    return None


def _decimal_odd(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("odd must be numeric")
    try:
        odd = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("odd must be numeric") from exc
    if not odd.is_finite() or odd <= 1:
        raise ValueError("odd must be finite and greater than one")
    return odd


@dataclass(frozen=True, slots=True)
class MarketObservation:
    market_observation_id: str
    fixture_id: str
    provider_fixture_id: int
    bookmaker_id: int
    bookmaker_name: str
    provider_bet_id: int
    provider_bet_name: str
    raw_selection: str
    parsed_line: Decimal | None
    odds: Decimal
    provider_updated_at: datetime | None
    captured_at: datetime
    lab_owner: str
    classifier_version: str
    raw_payload: dict[str, Any]


def _observation_id(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "quantlab-market-v1:" + sha256(canonical).hexdigest()


def parse_market_response(
    response: Mapping[str, Any],
    *,
    fixture_id: str,
    provider_fixture_id: int,
    captured_at: datetime,
) -> tuple[MarketObservation, ...]:
    """Retain every returned market/selection for Bet365 and 1xBet, including unknown markets."""
    captured = _aware_utc(captured_at, "captured_at")
    if not isinstance(response, Mapping):
        raise TypeError("response must be a mapping")
    errors = response.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")
    records = response.get("response", [])
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise TypeError("API-Football odds response must contain a response list")

    observations: list[MarketObservation] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        fixture = record.get("fixture")
        if not isinstance(fixture, Mapping) or fixture.get("id") != provider_fixture_id:
            raise ValueError("odds response fixture does not match requested fixture")
        bookmakers = record.get("bookmakers", [])
        if not isinstance(bookmakers, list):
            continue
        for bookmaker in bookmakers:
            if not isinstance(bookmaker, Mapping):
                continue
            bookmaker_id = bookmaker.get("id")
            if bookmaker_id not in BOOKMAKERS:
                continue
            bookmaker_name = str(bookmaker.get("name") or BOOKMAKERS[int(bookmaker_id)]).strip()
            bets = bookmaker.get("bets", [])
            if not isinstance(bets, list):
                continue
            for bet in bets:
                if not isinstance(bet, Mapping):
                    continue
                bet_id = bet.get("id")
                bet_name = bet.get("name")
                if isinstance(bet_id, bool) or not isinstance(bet_id, int) or bet_id <= 0:
                    continue
                if not isinstance(bet_name, str) or not bet_name.strip():
                    continue
                classification = classify_market(bet_id, bet_name)
                values = bet.get("values", [])
                if not isinstance(values, list):
                    continue
                for value in values:
                    if not isinstance(value, Mapping):
                        continue
                    selection = value.get("value")
                    if not isinstance(selection, str) or not selection.strip():
                        continue
                    try:
                        odds = _decimal_odd(value.get("odd"))
                    except ValueError:
                        continue
                    provider_updated_at = _parse_datetime(
                        value.get("update") or bookmaker.get("update") or record.get("update")
                    )
                    raw_payload = {
                        "fixture": dict(fixture),
                        "bookmaker": {"id": bookmaker_id, "name": bookmaker_name},
                        "bet": {"id": bet_id, "name": bet_name},
                        "value": dict(value),
                        "record_update": record.get("update"),
                        "bookmaker_update": bookmaker.get("update"),
                    }
                    identity_payload = {
                        "fixture_id": fixture_id,
                        "provider_fixture_id": provider_fixture_id,
                        "bookmaker_id": bookmaker_id,
                        "provider_bet_id": bet_id,
                        "provider_bet_name": bet_name,
                        "selection": selection.strip(),
                        "odds": str(odds),
                        "provider_updated_at": provider_updated_at.isoformat()
                        if provider_updated_at
                        else None,
                        "captured_at": captured.isoformat(),
                    }
                    observations.append(
                        MarketObservation(
                            market_observation_id=_observation_id(identity_payload),
                            fixture_id=fixture_id,
                            provider_fixture_id=provider_fixture_id,
                            bookmaker_id=int(bookmaker_id),
                            bookmaker_name=bookmaker_name,
                            provider_bet_id=bet_id,
                            provider_bet_name=bet_name.strip(),
                            raw_selection=selection.strip(),
                            parsed_line=parse_line(selection),
                            odds=odds,
                            provider_updated_at=provider_updated_at,
                            captured_at=captured,
                            lab_owner=classification.owner,
                            classifier_version=CLASSIFIER_VERSION,
                            raw_payload=raw_payload,
                        )
                    )
    return tuple(observations)


class QuantLabMarketCollector:
    def __init__(self, repository: Any, provider: Any) -> None:
        self._repository = repository
        self._provider = provider

    def collect_fixture(
        self,
        *,
        fixture_id: str,
        provider_fixture_id: int,
        captured_at: datetime,
    ) -> tuple[MarketObservation, ...]:
        payload = self._provider.fetch_odds(provider_fixture_id)
        observations = parse_market_response(
            payload,
            fixture_id=fixture_id,
            provider_fixture_id=provider_fixture_id,
            captured_at=captured_at,
        )
        self._repository.save_market_observations(observations)
        return observations
