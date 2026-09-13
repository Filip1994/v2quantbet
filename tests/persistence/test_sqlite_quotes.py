from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.odds.quote_deduplication import QuoteConflictError
from h2h.persistence import SQLiteQuoteRepository

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


def test_round_trip_and_fixture_query() -> None:
    repository = SQLiteQuoteRepository(":memory:")
    first = quote()
    second = quote(fixture_id="fixture-2")

    repository.save((first, second))

    assert repository.all() == (first, second)
    assert repository.for_fixture("fixture-1") == (first,)
    repository.close()


def test_identical_duplicates_are_idempotent() -> None:
    repository = SQLiteQuoteRepository(":memory:")
    first = quote()

    repository.save((first, first))

    assert repository.all() == (first,)
    repository.close()


def test_conflict_is_rejected_atomically() -> None:
    repository = SQLiteQuoteRepository(":memory:")
    first = quote()
    repository.save((first,))

    with pytest.raises(QuoteConflictError):
        repository.save((quote(odd=2.2), quote(fixture_id="fixture-2")))

    assert repository.all() == (first,)
    repository.close()


def test_data_survives_reopen(tmp_path) -> None:
    database = tmp_path / "quotes.sqlite"
    first = quote()

    repository = SQLiteQuoteRepository(database)
    repository.save((first,))
    repository.close()

    reopened = SQLiteQuoteRepository(database)
    assert reopened.all() == (first,)
    reopened.close()
