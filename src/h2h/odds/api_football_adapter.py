"""API-Football odds adapter for the canonical QuantBet quote contract."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError


class ApiFootballQuoteAdapter:
    """Translate one flattened API-Football odds value into a canonical quote.

    The adapter intentionally accepts one bookmaker/bet/value combination rather
    than the complete API response. Traversing the provider response is kept
    outside the domain model and can be handled by an ingestion orchestration
    layer.
    """

    _BTTS_BET_ID = 8
    _OU25_BET_IDS = frozenset({5})

    def adapt(self, payload: Mapping[str, Any]) -> CanonicalQuote:
        """Convert one flattened API-Football quote into ``CanonicalQuote``."""
        try:
            fixture = self._mapping(payload, "fixture")
            bookmaker = self._mapping(payload, "bookmaker")
            bet = self._mapping(payload, "bet")
            value = self._mapping(payload, "value")

            fixture_id = str(fixture["id"])
            bookmaker_id = int(bookmaker["id"])
            bookmaker_name = str(bookmaker["name"])
            bet_id = int(bet["id"])
            selection_value = str(value["value"])
            odd = float(value["odd"])
            observed_at = self._parse_datetime(
                payload.get("observed_at") or payload.get("update")
            )

            market, selection = self._map_market_selection(bet_id, selection_value)
            return CanonicalQuote(
                fixture_id=fixture_id,
                bookmaker_id=bookmaker_id,
                bookmaker_name=bookmaker_name,
                market=market,
                selection=selection,
                odd=odd,
                observed_at=observed_at,
                source="api-football",
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise QuoteNormalizationError(
                f"invalid API-Football odds payload: {exc}"
            ) from exc

    @staticmethod
    def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        value = payload[key]
        if not isinstance(value, Mapping):
            raise TypeError(f"{key} must be a mapping")
        return value

    @classmethod
    def _map_market_selection(
        cls, bet_id: int, provider_selection: str
    ) -> tuple[Market, Selection]:
        if bet_id == cls._BTTS_BET_ID:
            selection_map = {"YES": Selection.YES, "NO": Selection.NO}
            market = Market.BTTS
        elif bet_id in cls._OU25_BET_IDS:
            selection_map = {"OVER 2.5": Selection.OVER, "UNDER 2.5": Selection.UNDER}
            market = Market.OU_25
        else:
            raise ValueError(f"unsupported API-Football bet id: {bet_id}")

        try:
            return market, selection_map[provider_selection.strip().upper()]
        except KeyError as exc:
            raise ValueError(
                f"unsupported selection {provider_selection!r} for bet {bet_id}"
            ) from exc

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("observed_at or update must be an ISO datetime string")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
