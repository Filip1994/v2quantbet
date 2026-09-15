from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.persistence.quote_history import InMemoryQuoteHistoryRepository, QuoteHistoryConflictError
from h2h.use_cases import QuoteHistoryIngestionService


def make_quote(
    odd: float = 2.1,
    *,
    fixture_id: str = "fixture-1",
) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id=fixture_id,
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


def test_changed_odd_conflicts_even_when_capture_changes() -> None:
    repository = InMemoryQuoteHistoryRepository()
    captures = iter(
        (
            datetime(2026, 9, 15, 12, 1, tzinfo=UTC),
            datetime(2026, 9, 15, 12, 2, tzinfo=UTC),
        )
    )
    service = QuoteHistoryIngestionService(repository, capture_clock=lambda: next(captures))

    service.ingest([make_quote(2.1)])
    with pytest.raises(QuoteHistoryConflictError, match="natural identity"):
        service.ingest([make_quote(2.2)])

    series = repository.series_for_fixture("fixture-1")
    snapshots = repository.snapshots_for_series(series[0].series_id)
    assert len(snapshots) == 1
    assert snapshots[0].odd == 2.1
    assert snapshots[0].captured_at == datetime(2026, 9, 15, 12, 1, tzinfo=UTC)


def test_canonical_fixture_id_flows_through_unchanged_history_hashing() -> None:
    repository = InMemoryQuoteHistoryRepository()
    service = QuoteHistoryIngestionService(
        repository,
        capture_clock=lambda: datetime(2026, 9, 15, 12, 1, tzinfo=UTC),
    )

    service.ingest([make_quote(fixture_id="api-football:123")])

    series = repository.series_for_fixture("api-football:123")
    assert len(series) == 1
    assert series[0].series_id == (
        "series-1cb7f716332a558035795ac53f0ba40c15e8984eb69d40aee54435a22f7c24c8"
    )
    snapshots = repository.snapshots_for_series(series[0].series_id)
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_id == (
        "snapshot-6502dee18fa5965714ef2559c6811adc8ca83f0c4310f3da99ecb9cebcb9ccfc"
    )
