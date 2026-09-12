import pytest

from datetime import UTC, datetime

from quantbet.domain.odds import CanonicalQuote, Market, Selection


OBSERVED_AT = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def make_quote(market=Market.OU_25, selection=Selection.OVER, odd=1.9):
    return CanonicalQuote(
        fixture_id="fixture-1",
        bookmaker_id=8,
        bookmaker_name="Example Bookmaker",
        market=market,
        selection=selection,
        odd=odd,
        observed_at=OBSERVED_AT,
        source="provider-x",
    )


@pytest.mark.parametrize(
    ("market", "selection"),
    [
        (Market.OU_25, Selection.OVER),
        (Market.OU_25, Selection.UNDER),
        (Market.BTTS, Selection.YES),
        (Market.BTTS, Selection.NO),
    ],
)
def test_valid_market_selection_pairs(market, selection):
    quote = make_quote(market=market, selection=selection)
    assert quote.market is market
    assert quote.selection is selection


@pytest.mark.parametrize(
    ("market", "selection"),
    [
        (Market.OU_25, Selection.YES),
        (Market.OU_25, Selection.NO),
        (Market.BTTS, Selection.OVER),
        (Market.BTTS, Selection.UNDER),
    ],
)
def test_invalid_market_selection_pairs(market, selection):
    with pytest.raises(ValueError):
        make_quote(market=market, selection=selection)


@pytest.mark.parametrize("odd", [1.0, 0.99, 0.0, -1.0])
def test_odd_must_be_greater_than_one(odd):
    with pytest.raises(ValueError):
        make_quote(odd=odd)


def test_quote_is_immutable():
    quote = make_quote()
    with pytest.raises(AttributeError):
        quote.odd = 2.0


def test_unsupported_market_is_rejected():
    with pytest.raises(ValueError):
        make_quote(market="CORRECT_SCORE")


def test_empty_required_text_is_rejected():
    with pytest.raises(ValueError):
        CanonicalQuote(
            fixture_id="",
            bookmaker_id=8,
            bookmaker_name="Bookmaker",
            market=Market.OU_25,
            selection=Selection.OVER,
            odd=1.9,
            observed_at=OBSERVED_AT,
            source="provider-x",
        )
