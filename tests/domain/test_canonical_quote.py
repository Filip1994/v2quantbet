from datetime import UTC, datetime
from math import inf, nan

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection

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


def test_quote_identity_excludes_observation_attributes():
    first = make_quote(odd=1.9)
    second = CanonicalQuote(
        fixture_id=first.fixture_id,
        bookmaker_id=first.bookmaker_id,
        bookmaker_name=first.bookmaker_name,
        market=first.market,
        selection=first.selection,
        odd=2.1,
        observed_at=datetime(2026, 9, 12, 13, 0, tzinfo=UTC),
        source="provider-y",
    )

    assert first.identity == second.identity


def test_quote_identity_contains_canonical_dimensions():
    quote = make_quote(market=Market.BTTS, selection=Selection.YES)

    assert quote.identity == ("fixture-1", 8, Market.BTTS, Selection.YES)


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


@pytest.mark.parametrize("odd", [nan, inf, -inf])
def test_odd_must_be_finite(odd):
    with pytest.raises(ValueError):
        make_quote(odd=odd)


def test_quote_is_immutable():
    quote = make_quote()
    with pytest.raises(AttributeError):
        quote.odd = 2.0


def test_unsupported_market_is_rejected():
    with pytest.raises(ValueError):
        make_quote(market="CORRECT_SCORE")


@pytest.mark.parametrize("field", ["fixture_id", "bookmaker_name", "source"])
def test_required_text_fields_must_not_be_blank(field):
    values = {
        "fixture_id": "fixture-1",
        "bookmaker_id": 8,
        "bookmaker_name": "Bookmaker",
        "market": Market.OU_25,
        "selection": Selection.OVER,
        "odd": 1.9,
        "observed_at": OBSERVED_AT,
        "source": "provider-x",
    }
    values[field] = "   "

    with pytest.raises(ValueError):
        CanonicalQuote(**values)


@pytest.mark.parametrize("bookmaker_id", [0, -1])
def test_bookmaker_id_must_be_positive(bookmaker_id):
    with pytest.raises(ValueError):
        CanonicalQuote(
            fixture_id="fixture-1",
            bookmaker_id=bookmaker_id,
            bookmaker_name="Bookmaker",
            market=Market.OU_25,
            selection=Selection.OVER,
            odd=1.9,
            observed_at=OBSERVED_AT,
            source="provider-x",
        )


def test_observed_at_must_be_datetime():
    with pytest.raises(TypeError):
        CanonicalQuote(
            fixture_id="fixture-1",
            bookmaker_id=8,
            bookmaker_name="Bookmaker",
            market=Market.OU_25,
            selection=Selection.OVER,
            odd=1.9,
            observed_at="2026-09-12T12:00:00Z",
            source="provider-x",
        )
