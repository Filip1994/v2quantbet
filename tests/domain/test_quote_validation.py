from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.quote_validation import validate_quotes

OBSERVED_AT = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


def quote(selection: Selection, *, market: Market = Market.OU_25) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id="fixture-1",
        bookmaker_id=10,
        bookmaker_name="Bookmaker",
        market=market,
        selection=selection,
        odd=2.0,
        observed_at=OBSERVED_AT,
        source="test",
    )


def test_validate_quotes_returns_canonical_tuple() -> None:
    quotes = (quote(Selection.OVER), quote(Selection.UNDER))

    assert validate_quotes(quotes) == quotes


def test_validate_quotes_rejects_empty_collection() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_quotes(())


def test_validate_quotes_rejects_mixed_fixture() -> None:
    other = CanonicalQuote(
        fixture_id="fixture-2",
        bookmaker_id=10,
        bookmaker_name="Bookmaker",
        market=Market.OU_25,
        selection=Selection.UNDER,
        odd=2.0,
        observed_at=OBSERVED_AT,
        source="test",
    )

    with pytest.raises(ValueError, match="same fixture"):
        validate_quotes((quote(Selection.OVER), other))


def test_validate_quotes_rejects_non_quote_values() -> None:
    with pytest.raises(TypeError, match="CanonicalQuote"):
        validate_quotes((quote(Selection.OVER), "not-a-quote"))
