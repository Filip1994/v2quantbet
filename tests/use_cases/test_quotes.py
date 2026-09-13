from datetime import UTC, datetime

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.persistence import InMemoryQuoteRepository
from h2h.use_cases import QuoteIngestionService

OBSERVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def make_quote(fixture_id: str = "fixture-1") -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id=fixture_id,
        bookmaker_id=10,
        bookmaker_name="Bookmaker",
        market=Market.OU_25,
        selection=Selection.OVER,
        odd=2.1,
        observed_at=OBSERVED_AT,
        source="test",
    )


def test_ingest_and_fixture_read_are_delegated_to_repository() -> None:
    service = QuoteIngestionService(InMemoryQuoteRepository())
    quote = make_quote()

    service.ingest([quote])

    assert service.read_fixture("fixture-1") == (quote,)
    assert service.read_fixture("missing") == ()


def test_read_all_returns_repository_order() -> None:
    service = QuoteIngestionService(InMemoryQuoteRepository())
    first = make_quote("fixture-1")
    second = make_quote("fixture-2")

    service.ingest([first, second])

    assert service.read_all() == (first, second)
