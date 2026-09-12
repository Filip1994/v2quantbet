from datetime import UTC, datetime

import pytest

from h2h.domain.market_snapshot import MarketSnapshot
from h2h.domain.odds import CanonicalQuote, Market, Selection

OBSERVED_AT = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


def quote(selection: Selection) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id="fixture-1",
        bookmaker_id=10,
        bookmaker_name="Bookmaker",
        market=Market.OU_25,
        selection=selection,
        odd=2.0,
        observed_at=OBSERVED_AT,
        source="test",
    )


def test_snapshot_requires_both_ou25_selections() -> None:
    snapshot = MarketSnapshot(
        fixture_id="fixture-1",
        bookmaker_id=10,
        market=Market.OU_25,
        observed_at=OBSERVED_AT,
        quotes=(quote(Selection.OVER), quote(Selection.UNDER)),
    )

    assert snapshot.quote_for(Selection.OVER).odd == 2.0


def test_snapshot_rejects_incomplete_market() -> None:
    with pytest.raises(ValueError, match="exactly"):
        MarketSnapshot(
            fixture_id="fixture-1",
            bookmaker_id=10,
            market=Market.OU_25,
            observed_at=OBSERVED_AT,
            quotes=(quote(Selection.OVER),),
        )


def test_snapshot_rejects_mismatched_quote_context() -> None:
    under = CanonicalQuote(
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
        MarketSnapshot(
            fixture_id="fixture-1",
            bookmaker_id=10,
            market=Market.OU_25,
            observed_at=OBSERVED_AT,
            quotes=(quote(Selection.OVER), under),
        )
