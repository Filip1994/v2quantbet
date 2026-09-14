from datetime import datetime, timezone

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot
from h2h.persistence.postgres_quote_history import PostgreSQLQuoteHistoryRepository

UTC = timezone.utc


def make_series() -> QuoteSeries:
    return QuoteSeries(
        series_id="series-1",
        fixture_id="fixture-1",
        bookmaker_id=10,
        market=Market.OU_25,
        selection=Selection.OVER,
        created_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
    )


def make_snapshot() -> QuoteSnapshot:
    return QuoteSnapshot(
        snapshot_id="snapshot-1",
        series_id="series-1",
        odd=2.10,
        observed_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        captured_at=datetime(2026, 9, 14, 12, 0, 1, tzinfo=UTC),
        source="api-football",
    )


def test_requires_database_url_without_injected_connection() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        PostgreSQLQuoteHistoryRepository(database_url="")


def test_injected_connection_factory_allows_driver_free_construction() -> None:
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: object())
    assert repository._connect() is not None


def test_row_conversion_reconstructs_domain_objects() -> None:
    series = make_series()
    snapshot = make_snapshot()

    restored_series = PostgreSQLQuoteHistoryRepository._row_to_series(
        (
            series.series_id,
            series.fixture_id,
            series.bookmaker_id,
            series.market.value,
            series.selection.value,
            series.created_at,
        )
    )
    restored_snapshot = PostgreSQLQuoteHistoryRepository._row_to_snapshot(
        (
            snapshot.snapshot_id,
            snapshot.series_id,
            snapshot.odd,
            snapshot.observed_at,
            snapshot.captured_at,
            snapshot.source,
        )
    )

    assert restored_series == series
    assert restored_snapshot == snapshot


def test_injected_connection_factory_takes_precedence_over_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid")
    connection = object()
    repository = PostgreSQLQuoteHistoryRepository(connect=lambda: connection)
    assert repository._connect() is connection
