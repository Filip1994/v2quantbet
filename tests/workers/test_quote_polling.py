from datetime import UTC, datetime

import pytest

from h2h.domain.fixture_identity import (
    ResolvedFixtureIdentity,
    api_football_fixture_identity,
)
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.persistence import InMemoryQuoteRepository
from h2h.use_cases import QuoteIngestionService
from h2h.workers.quote_polling import QuotePollingJob


class FakeSource:
    def __init__(
        self,
        quotes_by_fixture: dict[str, tuple[CanonicalQuote, ...]],
    ) -> None:
        self.quotes_by_fixture = quotes_by_fixture
        self.requested: list[ResolvedFixtureIdentity] = []

    def fetch_quotes(
        self,
        *,
        fixture_identity: ResolvedFixtureIdentity,
    ) -> tuple[CanonicalQuote, ...]:
        self.requested.append(fixture_identity)
        return self.quotes_by_fixture[fixture_identity.fixture_id]


def quote(fixture_id: int, bookmaker_id: int) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id=api_football_fixture_identity(fixture_id).fixture_id,
        bookmaker_id=bookmaker_id,
        bookmaker_name="Test bookmaker",
        market=Market.OU_25,
        selection=Selection.OVER,
        odd=2.1,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        source="test",
    )


def test_polling_job_fetches_each_fixture_and_ingests_quotes() -> None:
    identities = (api_football_fixture_identity(1), api_football_fixture_identity(2))
    source = FakeSource(
        {
            identities[0].fixture_id: (quote(1, 10),),
            identities[1].fixture_id: (quote(2, 20), quote(2, 21)),
        }
    )
    repository = InMemoryQuoteRepository()
    job = QuotePollingJob(source, QuoteIngestionService(repository), identities)

    assert job.run_once() == 3
    assert source.requested == list(identities)
    assert len(repository.all()) == 3


def test_polling_job_rejects_raw_fixture_ids() -> None:
    with pytest.raises(TypeError, match="ResolvedFixtureIdentity"):
        QuotePollingJob(
            FakeSource({}),
            QuoteIngestionService(InMemoryQuoteRepository()),
            [1],  # type: ignore[list-item]
        )
