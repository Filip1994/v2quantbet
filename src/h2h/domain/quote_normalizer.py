"""Normalize provider odds payloads into canonical quote observations."""

from collections.abc import Mapping

from .odds import CanonicalQuote, Market, Selection


_MARKET_MAP = {
    "OU_25": Market.OU_25,
    "TOTALS_2_5": Market.OU_25,
    "BTTS": Market.BTTS,
}
_SELECTION_MAP = {
    "OVER": Selection.OVER,
    "UNDER": Selection.UNDER,
    "YES": Selection.YES,
    "NO": Selection.NO,
}


class QuoteNormalizationError(ValueError):
    """Raised when a provider quote cannot be normalized safely."""


def _required(payload: Mapping[str, object], field: str) -> object:
    try:
        return payload[field]
    except KeyError as exc:
        raise QuoteNormalizationError(f"missing required field: {field}") from exc


def normalize_quote(payload: Mapping[str, object]) -> CanonicalQuote:
    """Convert one provider-neutral payload into a validated canonical quote."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")

    raw_market = _required(payload, "market")
    raw_selection = _required(payload, "selection")

    try:
        market = _MARKET_MAP[str(raw_market).strip().upper()]
    except KeyError as exc:
        raise QuoteNormalizationError(f"unsupported market: {raw_market!r}") from exc

    try:
        selection = _SELECTION_MAP[str(raw_selection).strip().upper()]
    except KeyError as exc:
        raise QuoteNormalizationError(
            f"unsupported selection: {raw_selection!r}"
        ) from exc

    try:
        return CanonicalQuote(
            fixture_id=str(_required(payload, "fixture_id")),
            bookmaker_id=int(_required(payload, "bookmaker_id")),
            bookmaker_name=str(_required(payload, "bookmaker_name")),
            market=market,
            selection=selection,
            odd=float(_required(payload, "odd")),
            observed_at=_required(payload, "observed_at"),
            source=str(_required(payload, "source")),
        )
    except (TypeError, ValueError) as exc:
        raise QuoteNormalizationError(str(exc)) from exc
