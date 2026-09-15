from datetime import UTC, datetime, timedelta

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.odds import QuoteConflictError, deduplicate_quotes


OBSERVED_AT = datetime(2026, 9, 13, 20, 3, 16, tzinfo=UTC)


def quote(*, odd: float = 2.2, observed_at: datetime = OBSERVED_AT) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id="fixture-1",
        bookmaker_id=7,
        bookmaker_name="William Hill",
        market=Market.BTTS,
        selection=Selection.YES,
        odd=odd,
        observed_at=observed_at,
        source="api-football",
    )


def test_exact_duplicate_is_collapsed() -> None:
    item = quote()
    assert deduplicate_quotes((item, item)) == (item,)


def test_distinct_selections_are_preserved() -> None:
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


def test_observations_at_different_times_are_preserved() -> None:
    first = quote(odd=2.2)
    second = quote(odd=2.3, observed_at=OBSERVED_AT + timedelta(minutes=5))
    assert deduplicate_quotes((first, second)) == (first, second)


def test_conflicting_observation_at_same_time_is_rejected() -> None:
    with pytest.raises(QuoteConflictError, match="conflicting observations"):
        deduplicate_quotes((quote(odd=2.2), quote(odd=2.3)))
