from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.persistence.quote_history import InMemoryQuoteHistoryRepository
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.workers.history_quote_polling import HistoryQuotePollingJob


class FakeSource:
    def __init__(self, quotes_by_fixture: dict[int, tuple[CanonicalQuote, ...]]) -> None:
        self.quotes_by_fixture = quotes_by_fixture
        self.requested: list[int] = []

    def fetch_quotes(self, *, fixture_id: int) -> tuple[CanonicalQuote, ...]:
        self.requested.append(fixture_id)
        return self.quotes_by_fixture[fixture_id]


def quote(fixture_id: int, odd: float) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id=fixture_id,
        bookmaker_id=10,
        bookmaker_name="Bookmaker",
        market=Market.OU_25,
        selection=Selection.OVER,
        odd=odd,
        observed_at=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        source="test",
    )


def test_polling_job_persists_history_for_all_fixtures() -> None:
    source = FakeSource({1: (quote(1, 2.1),), 2: (quote(2, 2.2),)})
    repository = InMemoryQuoteHistoryRepository()
    ingestion = QuoteHistoryIngestionService(
        repository, capture_clock=lambda: datetime(2026, 9, 15, 12, 1, tzinfo=UTC)
    )

    job = HistoryQuotePollingJob(source, ingestion, [1, 2])

    assert job.run_once() == 2
    assert source.requested == [1, 2]
    assert len(repository.series_for_fixture("1")) == 1
    assert len(repository.series_for_fixture("2")) == 1


def test_polling_job_rejects_invalid_fixture_ids() -> None:
    repository = InMemoryQuoteHistoryRepository()
    ingestion = QuoteHistoryIngestionService(
        repository, capture_clock=lambda: datetime.now(UTC)
    )

    with pytest.raises(ValueError, match="positive integers"):
        HistoryQuotePollingJob(FakeSource({}), ingestion, [0])
