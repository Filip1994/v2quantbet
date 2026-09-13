from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.odds import QuoteConflictError, deduplicate_quotes


def quote(*, odd: float = 2.2) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id="fixture-1",
        bookmaker_id=7,
        bookmaker_name="William Hill",
        market=Market.BTTS,
        selection=Selection.YES,
        odd=odd,
        observed_at=datetime(2026, 9, 13, 20, 3, 16, tzinfo=UTC),
        source="api-football",
    )


def test_exact_duplicate_is_collapsed() -> None:
    item = quote()
    assert deduplicate_quotes((item, item)) == (item,)


def test_distinct_identities_are_preserved() -> None:
    first = quote()
    second = CanonicalQuote(
        fixture_id=first.fixture_id,
        bookmaker_id=first.bookmaker_id,
        bookmaker_name=first.bookmaker_name,
        market=first.market,
        selection=Selection.NO,
        odd=1.62,
        observed_at=first.observed_at,
        source=first.source,
    )
    assert deduplicate_quotes((first, second)) == (first, second)


def test_conflicting_observation_is_rejected() -> None:
    with pytest.raises(QuoteConflictError, match="conflicting observations"):
        deduplicate_quotes((quote(odd=2.2), quote(odd=2.3)))
