from datetime import UTC, datetime

import pytest

from h2h.domain.bookmaker_policy import UnsupportedBookmakerError
from h2h.domain.odds import Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.odds import ApiFootballQuoteAdapter


@pytest.fixture
def adapter() -> ApiFootballQuoteAdapter:
    return ApiFootballQuoteAdapter()


def payload(
    *,
    bookmaker_id: int = 8,
    bookmaker_name: str = "Bet365",
    bet_id: int = 8,
    selection: str = "Yes",
    odd: object = "2.20",
    update: object = "2026-09-13T20:03:16+00:00",
) -> dict:
    return {
        "fixture": {"id": 1493129, "date": "2026-09-14T00:30:00+00:00"},
        "bookmaker": {"id": bookmaker_id, "name": bookmaker_name},
        "bet": {"id": bet_id, "name": "Both Teams Score"},
        "value": {"value": selection, "odd": odd},
        "update": update,
    }


def test_adapts_api_football_btts_quote(adapter: ApiFootballQuoteAdapter) -> None:
    quote = adapter.adapt(payload())

    assert quote.fixture_id == "1493129"
    assert quote.bookmaker_id == 8
    assert quote.bookmaker_name == "Bet365"
    assert quote.market is Market.BTTS
    assert quote.selection is Selection.YES
    assert quote.odd == 2.20
    assert quote.observed_at == datetime(2026, 9, 13, 20, 3, 16, tzinfo=UTC)
    assert quote.source == "api-football"


@pytest.mark.parametrize(
    ("bookmaker_id", "bookmaker_name"),
    [(8, "Bet365"), (11, "1xBet"), (34, "Superbet")],
)
def test_accepts_approved_api_football_bookmakers(
    adapter: ApiFootballQuoteAdapter,
    bookmaker_id: int,
    bookmaker_name: str,
) -> None:
    quote = adapter.adapt(
        payload(bookmaker_id=bookmaker_id, bookmaker_name=bookmaker_name)
    )

    assert quote.bookmaker_id == bookmaker_id
    assert quote.bookmaker_name == bookmaker_name


def test_rejects_unsupported_api_football_bookmaker(
    adapter: ApiFootballQuoteAdapter,
) -> None:
    with pytest.raises(UnsupportedBookmakerError, match="unsupported API-Football"):
        adapter.adapt(payload(bookmaker_id=7, bookmaker_name="William Hill"))


def test_rejects_api_football_bookmaker_name_mismatch(
    adapter: ApiFootballQuoteAdapter,
) -> None:
    with pytest.raises(UnsupportedBookmakerError, match="id/name mismatch"):
        adapter.adapt(payload(bookmaker_id=8, bookmaker_name="William Hill"))


def test_adapts_api_football_btts_no_selection(adapter: ApiFootballQuoteAdapter) -> None:
    quote = adapter.adapt(payload(selection="No", odd="1.62"))

    assert quote.market is Market.BTTS
    assert quote.selection is Selection.NO
    assert quote.odd == 1.62


@pytest.mark.parametrize("odd", [2.2, 2, "2.20", " 2.20 "])
def test_accepts_valid_numeric_odd_forms(
    adapter: ApiFootballQuoteAdapter,
    odd: object,
) -> None:
    assert adapter.adapt(payload(odd=odd)).odd == 2.2


@pytest.mark.parametrize("odd", [True, "", "not-a-number", "nan", "inf", float("nan"), float("inf")])
def test_rejects_invalid_odd_forms(
    adapter: ApiFootballQuoteAdapter,
    odd: object,
) -> None:
    with pytest.raises(QuoteNormalizationError):
        adapter.adapt(payload(odd=odd))


@pytest.mark.parametrize("field_value", [True, 8.0, "8", 0, -1])
def test_rejects_invalid_bookmaker_id(adapter: ApiFootballQuoteAdapter, field_value: object) -> None:
    with pytest.raises(QuoteNormalizationError):
        adapter.adapt(payload(bookmaker_id=field_value))  # type: ignore[arg-type]


def test_rejects_empty_bookmaker_name(adapter: ApiFootballQuoteAdapter) -> None:
    with pytest.raises(QuoteNormalizationError):
        adapter.adapt(payload(bookmaker_name="   "))


def test_rejects_naive_update_timestamp(adapter: ApiFootballQuoteAdapter) -> None:
    with pytest.raises(QuoteNormalizationError, match="timezone-aware"):
        adapter.adapt(payload(update="2026-09-13T20:03:16"))


def test_rejects_invalid_payload_shape(adapter: ApiFootballQuoteAdapter) -> None:
    with pytest.raises(QuoteNormalizationError):
        adapter.adapt([])  # type: ignore[arg-type]


def test_rejects_unsupported_bet(adapter: ApiFootballQuoteAdapter) -> None:
    with pytest.raises(QuoteNormalizationError, match="unsupported API-Football bet id"):
        adapter.adapt(payload(bet_id=1))
