"""API-Football odds adapter for the canonical QuantBet quote contract."""

from collections.abc import Mapping
from datetime import datetime
import math
import re
from typing import Any

from h2h.domain.bookmaker_policy import (
    UnsupportedBookmakerError,
    resolve_api_football_bookmaker,
)
from h2h.domain.fixture_identity import (
    ResolvedFixtureIdentity,
    api_football_provider_fixture_id,
)
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError


API_FOOTBALL_PREMATCH_BET_IDS = {
    Market.OU_25: 5,
    Market.BTTS: 8,
}


def api_football_bet_id_for_market(market: Market) -> int:
    try:
        return API_FOOTBALL_PREMATCH_BET_IDS[market]
    except KeyError as exc:
        raise ValueError(f"unsupported canonical market: {market!r}") from exc


class ApiFootballQuoteAdapter:
    """Translate one flattened API-Football odds value into a canonical quote."""

    _BTTS_BET_ID = API_FOOTBALL_PREMATCH_BET_IDS[Market.BTTS]
    _OU25_BET_IDS = frozenset({API_FOOTBALL_PREMATCH_BET_IDS[Market.OU_25]})

    def adapt(
        self,
        payload: Mapping[str, Any],
        *,
        fixture_identity: ResolvedFixtureIdentity,
    ) -> CanonicalQuote:
        """Convert one flattened API-Football quote into CanonicalQuote."""
        try:
            if not isinstance(payload, Mapping):
                raise TypeError("payload must be a mapping")
            fixture = self._mapping(payload, "fixture")
            bookmaker = self._mapping(payload, "bookmaker")
            bet = self._mapping(payload, "bet")
            value = self._mapping(payload, "value")

            fixture_id = self._positive_int(fixture.get("id"), "fixture.id")
            requested_fixture_id = api_football_provider_fixture_id(fixture_identity)
            if fixture_id != requested_fixture_id:
                raise ValueError(
                    "fixture.id does not match the requested API-Football fixture"
                )
            bookmaker_id = self._positive_int(bookmaker.get("id"), "bookmaker.id")
            bookmaker_name = self._nonempty_string(bookmaker.get("name"), "bookmaker.name")
            bookmaker_identity = resolve_api_football_bookmaker(bookmaker_id, bookmaker_name)
            bet_id = self._positive_int(bet.get("id"), "bet.id")
            bet_name = self._nonempty_string(bet.get("name"), "bet.name")
            selection_value = self._nonempty_string(value.get("value"), "value.value")
            odd = self._finite_float(value.get("odd"), "value.odd")
            observed_at = self._parse_datetime(payload.get("observed_at") or payload.get("update"))

            market, selection = self._map_market_selection(
                bet_id,
                bet_name,
                selection_value,
            )
            return CanonicalQuote(
                fixture_id=fixture_identity.fixture_id,
                bookmaker_id=bookmaker_identity.provider_id,
                bookmaker_name=bookmaker_identity.provider_name,
                market=market,
                selection=selection,
                odd=odd,
                observed_at=observed_at,
                source="api-football",
            )
        except UnsupportedBookmakerError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise QuoteNormalizationError(f"invalid API-Football odds payload: {exc}") from exc

    @staticmethod
    def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        value = payload[key]
        if not isinstance(value, Mapping):
            raise TypeError(f"{key} must be a mapping")
        return value

    @staticmethod
    def _positive_int(value: Any, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise TypeError(f"{field} must be a positive integer")
        return value

    @staticmethod
    def _nonempty_string(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"{field} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _finite_float(value: Any, field: str) -> float:
        if isinstance(value, bool):
            raise TypeError(f"{field} must be numeric")
        if isinstance(value, str):
            if not value.strip():
                raise TypeError(f"{field} must be numeric")
            try:
                result = float(value)
            except ValueError as exc:
                raise TypeError(f"{field} must be numeric") from exc
        elif isinstance(value, (int, float)):
            result = float(value)
        else:
            raise TypeError(f"{field} must be numeric")
        if not math.isfinite(result):
            raise ValueError(f"{field} must be finite")
        return result

    @staticmethod
    def _normalized_bet_name(value: str) -> str:
        return " ".join(re.findall(r"[A-Z0-9]+", value.upper()))

    @classmethod
    def _validate_bet_identity(cls, bet_id: int, provider_bet_name: str) -> None:
        """Fail closed when provider bet ID and human-readable market name disagree."""
        normalized = cls._normalized_bet_name(provider_bet_name)
        tokens = set(normalized.split())
        if bet_id == cls._BTTS_BET_ID:
            valid = (
                "BOTH" in tokens
                and bool({"TEAM", "TEAMS"} & tokens)
                and ("SCORE" in tokens or "SCORING" in tokens)
            )
        elif bet_id in cls._OU25_BET_IDS:
            valid = "OVER" in tokens and "UNDER" in tokens
        else:
            raise ValueError(f"unsupported API-Football bet id: {bet_id}")
        if not valid:
            raise ValueError(
                f"API-Football bet id/name mismatch: id={bet_id}, name={provider_bet_name!r}"
            )

    @classmethod
    def _map_market_selection(
        cls,
        bet_id: int,
        provider_bet_name: str,
        provider_selection: str,
    ) -> tuple[Market, Selection]:
        cls._validate_bet_identity(bet_id, provider_bet_name)
        if bet_id == cls._BTTS_BET_ID:
            selection_map = {"YES": Selection.YES, "NO": Selection.NO}
            market = Market.BTTS
        elif bet_id in cls._OU25_BET_IDS:
            selection_map = {"OVER 2.5": Selection.OVER, "UNDER 2.5": Selection.UNDER}
            market = Market.OU_25
        else:
            raise ValueError(f"unsupported API-Football bet id: {bet_id}")

        try:
            return market, selection_map[provider_selection.upper()]
        except KeyError as exc:
            raise ValueError(f"unsupported selection {provider_selection!r} for bet {bet_id}") from exc

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("observed_at or update must be an ISO datetime string")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("observed_at or update must be a valid ISO datetime string") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("observed_at or update must be timezone-aware")
        return parsed
