from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.persistence import InMemoryQuoteRepository
from h2h.use_cases import QuoteIngestionService
from h2h.workers.quote_polling import QuotePollingJob


class FakeSource:
    def __init__(self, quotes_by_fixture: dict[int, tuple[CanonicalQuote, ...]]) -> None:
        self.quotes_by_fixture = quotes_by_fixture
        self.requested: list[int] = []

    def fetch_quotes(self, *, fixture_id: int) -> tuple[CanonicalQuote, ...]:
        self.requested.append(fixture_id)
        return self.quotes_by_fixture[fixture_id]


def quote(fixture_id: int, bookmaker_id: int) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id=str(fixture_id),
        bookmaker_id=bookmaker_id,
        bookmaker_name="Test bookmaker",
        market=Market.OU_25,
        selection=Selection.OVER,
        odd=2.1,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        source="test",
    )


def test_polling_job_fetches_each_fixture_and_ingests_quotes() -> None:
    source = FakeSource({1: (quote(1, 10),), 2: (quote(2, 20), quote(2, 21))})
    repository = InMemoryQuoteRepository()
    job = QuotePollingJob(source, QuoteIngestionService(repository), [1, 2])

    assert job.run_once() == 3
    assert source.requested == [1, 2]
    assert len(repository.all()) == 3


def test_polling_job_rejects_non_positive_fixture_ids() -> None:
    with pytest.raises(ValueError, match="positive integers"):
        QuotePollingJob(FakeSource({}), QuoteIngestionService(InMemoryQuoteRepository()), [0])
