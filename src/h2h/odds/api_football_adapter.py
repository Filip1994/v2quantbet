"""API-Football odds adapter for the canonical QuantBet quote contract."""

from collections.abc import Mapping
from datetime import datetime
import math
from typing import Any

from h2h.domain.bookmaker_policy import resolve_api_football_bookmaker
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError


class ApiFootballQuoteAdapter:
    """Translate one flattened API-Football odds value into a canonical quote."""

    _BTTS_BET_ID = 8
    _OU25_BET_IDS = frozenset({5})

    def adapt(self, payload: Mapping[str, Any]) -> CanonicalQuote:
        """Convert one flattened API-Football quote into ``CanonicalQuote``."""
        try:
            if not isinstance(payload, Mapping):
                raise TypeError("payload must be a mapping")
            fixture = self._mapping(payload, "fixture")
            bookmaker = self._mapping(payload, "bookmaker")
            bet = self._mapping(payload, "bet")
            value = self._mapping(payload, "value")

            fixture_id = self._positive_int(fixture.get("id"), "fixture.id")
            bookmaker_id = self._positive_int(bookmaker.get("id"), "bookmaker.id")
            bookmaker_name = self._nonempty_string(bookmaker.get("name"), "bookmaker.name")
            bookmaker_identity = resolve_api_football_bookmaker(bookmaker_id, bookmaker_name)
            bet_id = self._positive_int(bet.get("id"), "bet.id")
            selection_value = self._nonempty_string(value.get("value"), "value.value")
            odd = self._finite_float(value.get("odd"), "value.odd")
            observed_at = self._parse_datetime(payload.get("observed_at") or payload.get("update"))

            market, selection = self._map_market_selection(bet_id, selection_value)
            return CanonicalQuote(
                fixture_id=str(fixture_id),
                bookmaker_id=bookmaker_identity.provider_id,
                bookmaker_name=bookmaker_identity.provider_name,
                market=market,
                selection=selection,
                odd=odd,
                observed_at=observed_at,
                source="api-football",
            )
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
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{field} must be numeric")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{field} must be finite")
        return result

    @classmethod
    def _map_market_selection(cls, bet_id: int, provider_selection: str) -> tuple[Market, Selection]:
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
        return datetime.fromisoformat(value)
