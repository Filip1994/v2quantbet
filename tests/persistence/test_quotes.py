from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.odds.quote_deduplication import QuoteConflictError
from h2h.persistence import InMemoryQuoteRepository


OBSERVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def quote(*, fixture_id: str = "fixture-1", odd: float = 2.1) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id=fixture_id,
        bookmaker_id=7,
        bookmaker_name="Bookmaker",
        market=Market.BTTS,
        selection=Selection.YES,
        odd=odd,
        observed_at=OBSERVED_AT,
        source="test",
    )


def test_save_and_query_quotes() -> None:
    repository = InMemoryQuoteRepository()
    first = quote()
    second = quote(fixture_id="fixture-2")

    repository.save((first, second))

    assert repository.all() == (first, second)
    assert repository.for_fixture("fixture-1") == (first,)


def test_identical_duplicates_are_idempotent() -> None:
    repository = InMemoryQuoteRepository()
    first = quote()

    repository.save((first, first))

    assert repository.all() == (first,)


def test_conflict_is_rejected_atomically() -> None:
    repository = InMemoryQuoteRepository()
    first = quote()
    repository.save((first,))

    with pytest.raises(QuoteConflictError):
        repository.save((quote(odd=2.2), quote(fixture_id="fixture-2")))

    assert repository.all() == (first,)
