from datetime import UTC, datetime

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.persistence.quote_history import InMemoryQuoteHistoryRepository
from h2h.use_cases import QuoteHistoryIngestionService


def make_quote(odd: float = 2.1) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id="fixture-1",
        bookmaker_id=7,
        bookmaker_name="Bookmaker",
        market=Market.OU_25,
        selection=Selection.OVER,
        odd=odd,
        observed_at=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        source="provider",
    )


def test_ingest_creates_series_and_snapshot() -> None:
    repository = InMemoryQuoteHistoryRepository()
    service = QuoteHistoryIngestionService(
        repository,
        capture_clock=lambda: datetime(2026, 9, 15, 12, 1, tzinfo=UTC),
    )

    assert service.ingest([make_quote()]) == 1
    series = repository.series_for_fixture("fixture-1")
    assert len(series) == 1
    snapshots = repository.snapshots_for_series(series[0].series_id)
    assert len(snapshots) == 1
    assert snapshots[0].odd == 2.1


def test_repeated_same_cycle_is_idempotent() -> None:
    repository = InMemoryQuoteHistoryRepository()
    service = QuoteHistoryIngestionService(
        repository,
        capture_clock=lambda: datetime(2026, 9, 15, 12, 1, tzinfo=UTC),
    )

    service.ingest([make_quote()])
    service.ingest([make_quote()])

    series = repository.series_for_fixture("fixture-1")
    assert len(repository.snapshots_for_series(series[0].series_id)) == 1


def test_changed_odd_creates_new_snapshot_when_capture_changes() -> None:
    repository = InMemoryQuoteHistoryRepository()
    captures = iter(
        (
            datetime(2026, 9, 15, 12, 1, tzinfo=UTC),
            datetime(2026, 9, 15, 12, 2, tzinfo=UTC),
        )
    )
    service = QuoteHistoryIngestionService(repository, capture_clock=lambda: next(captures))

    service.ingest([make_quote(2.1)])
    service.ingest([make_quote(2.2)])

    series = repository.series_for_fixture("fixture-1")
    assert len(repository.snapshots_for_series(series[0].series_id)) == 2
