from datetime import datetime, timezone

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.odds import ApiFootballQuoteAdapter


@pytest.fixture
def adapter() -> ApiFootballQuoteAdapter:
    return ApiFootballQuoteAdapter()


def payload(*, bet_id: int = 8, selection: str = "Yes", odd: str = "2.20") -> dict:
    return {
        "fixture": {"id": 1493129, "date": "2026-09-14T00:30:00+00:00"},
        "bookmaker": {"id": 7, "name": "William Hill"},
        "bet": {"id": bet_id, "name": "Both Teams Score"},
        "value": {"value": selection, "odd": odd},
        "update": "2026-09-13T20:03:16+00:00",
    }


def test_adapts_api_football_btts_quote(adapter: ApiFootballQuoteAdapter) -> None:
    quote = adapter.adapt(payload())

    assert quote.fixture_id == "1493129"
    assert quote.bookmaker_id == 7
    assert quote.bookmaker_name == "William Hill"
    assert quote.market is Market.BTTS
    assert quote.selection is Selection.YES
    assert quote.odd == 2.20
    assert quote.observed_at == datetime(2026, 9, 13, 20, 3, 16, tzinfo=timezone.utc)
    assert quote.source == "api-football"


def test_adapts_api_football_btts_no_selection(adapter: ApiFootballQuoteAdapter) -> None:
    quote = adapter.adapt(payload(selection="No", odd="1.62"))

    assert quote.market is Market.BTTS
    assert quote.selection is Selection.NO
    assert quote.odd == 1.62


def test_rejects_unsupported_bet(adapter: ApiFootballQuoteAdapter) -> None:
    with pytest.raises(QuoteNormalizationError, match="unsupported API-Football bet id"):
        adapter.adapt(payload(bet_id=1))


def test_rejects_invalid_odd(adapter: ApiFootballQuoteAdapter) -> None:
    with pytest.raises(QuoteNormalizationError):
        adapter.adapt(payload(odd="not-a-number"))
