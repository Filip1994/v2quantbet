from datetime import UTC, datetime

import pytest

from h2h.domain.market_snapshot import MarketSnapshot
from h2h.domain.odds import CanonicalQuote, Market, Selection

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


def test_snapshot_requires_both_ou25_selections() -> None:
    snapshot = MarketSnapshot(
        fixture_id="fixture-1",
        bookmaker_id=10,
        market=Market.OU_25,
        observed_at=OBSERVED_AT,
        quotes=(quote(Selection.OVER), quote(Selection.UNDER)),
    )

    assert snapshot.quote_for(Selection.OVER).odd == 2.0


def test_snapshot_requires_both_btts_selections() -> None:
    snapshot = MarketSnapshot(
        fixture_id="fixture-1",
        bookmaker_id=10,
        market=Market.BTTS,
        observed_at=OBSERVED_AT,
        quotes=(
            quote(Selection.YES, market=Market.BTTS),
            quote(Selection.NO, market=Market.BTTS),
        ),
    )

    assert snapshot.quote_for(Selection.NO).selection is Selection.NO


def test_snapshot_can_derive_shared_context_from_quotes() -> None:
    snapshot = MarketSnapshot.from_quotes(
        (quote(Selection.OVER), quote(Selection.UNDER))
    )

    assert snapshot.fixture_id == "fixture-1"
    assert snapshot.bookmaker_id == 10
    assert snapshot.market is Market.OU_25
    assert snapshot.observed_at == OBSERVED_AT


def test_snapshot_from_quotes_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        MarketSnapshot.from_quotes(())


def test_snapshot_quote_for_rejects_missing_selection() -> None:
    snapshot = MarketSnapshot(
        fixture_id="fixture-1",
        bookmaker_id=10,
        market=Market.OU_25,
        observed_at=OBSERVED_AT,
        quotes=(quote(Selection.OVER), quote(Selection.UNDER)),
    )

    with pytest.raises(KeyError):
        snapshot.quote_for(Selection.YES)


def test_snapshot_rejects_incomplete_market() -> None:
    with pytest.raises(ValueError, match="exactly"):
        MarketSnapshot(
            fixture_id="fixture-1",
            bookmaker_id=10,
            market=Market.OU_25,
            observed_at=OBSERVED_AT,
            quotes=(quote(Selection.OVER),),
        )


def test_snapshot_rejects_duplicate_selection() -> None:
    with pytest.raises(ValueError, match="exactly"):
        MarketSnapshot(
            fixture_id="fixture-1",
            bookmaker_id=10,
            market=Market.OU_25,
            observed_at=OBSERVED_AT,
            quotes=(quote(Selection.OVER), quote(Selection.OVER)),
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
