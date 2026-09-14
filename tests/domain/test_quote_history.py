from datetime import UTC, datetime

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot


def test_quote_series_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        QuoteSeries(
            series_id="series-1",
            fixture_id="fixture-1",
            bookmaker_id=10,
            market=Market.OU_25,
            selection=Selection.OVER,
            created_at=datetime(2026, 9, 14, 12, 0),  # noqa: DTZ001
        )


def test_quote_snapshot_is_immutable_and_timestamped() -> None:
    snapshot = QuoteSnapshot(
        snapshot_id="snapshot-1",
        series_id="series-1",
        odd=2.15,
        observed_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        captured_at=datetime(2026, 9, 14, 12, 0, 1, tzinfo=UTC),
        source="api-football",
    )

    assert snapshot.odd == 2.15
    assert snapshot.observed_at.tzinfo is UTC
    assert snapshot.captured_at.tzinfo is UTC

    with pytest.raises(AttributeError):
        snapshot.odd = 2.20  # type: ignore[misc]


def test_quote_snapshot_rejects_invalid_odd() -> None:
    with pytest.raises(ValueError, match="greater than 1.0"):
        QuoteSnapshot(
            snapshot_id="snapshot-1",
            series_id="series-1",
            odd=1.0,
            observed_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            captured_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
            source="api-football",
        )
