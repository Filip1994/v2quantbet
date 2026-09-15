from datetime import UTC, datetime

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_history import QuoteSeries, QuoteSnapshot


def _series(**overrides) -> QuoteSeries:
    values = {
        "series_id": "series-1",
        "fixture_id": "fixture-1",
        "bookmaker_id": 10,
        "market": Market.OU_25,
        "selection": Selection.OVER,
        "created_at": datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return QuoteSeries(**values)


def _snapshot(**overrides) -> QuoteSnapshot:
    values = {
        "snapshot_id": "snapshot-1",
        "series_id": "series-1",
        "odd": 2.15,
        "observed_at": datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        "captured_at": datetime(2026, 9, 14, 12, 0, 1, tzinfo=UTC),
        "source": "api-football",
    }
    values.update(overrides)
    return QuoteSnapshot(**values)


def test_quote_series_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _series(created_at=datetime(2026, 9, 14, 12, 0))  # noqa: DTZ001


def test_quote_series_rejects_invalid_types() -> None:
    with pytest.raises(TypeError, match="series_id must be a string"):
        _series(series_id=123)
    with pytest.raises(TypeError, match="fixture_id must be a string"):
        _series(fixture_id=123)
    with pytest.raises(TypeError, match="bookmaker_id must be an int"):
        _series(bookmaker_id=True)
    with pytest.raises(TypeError, match="bookmaker_id must be an int"):
        _series(bookmaker_id=10.0)
    with pytest.raises(TypeError, match="market must be a Market"):
        _series(market="OU_25")
    with pytest.raises(TypeError, match="selection must be a Selection"):
        _series(selection="OVER")


def test_quote_snapshot_is_immutable_and_timestamped() -> None:
    snapshot = _snapshot()
    assert snapshot.odd == 2.15
    assert snapshot.observed_at.tzinfo is UTC
    assert snapshot.captured_at.tzinfo is UTC

    with pytest.raises(AttributeError):
        snapshot.odd = 2.20  # type: ignore[misc]


def test_quote_snapshot_rejects_invalid_types() -> None:
    with pytest.raises(TypeError, match="snapshot_id must be a string"):
        _snapshot(snapshot_id=123)
    with pytest.raises(TypeError, match="series_id must be a string"):
        _snapshot(series_id=123)
    with pytest.raises(TypeError, match="odd must be a number"):
        _snapshot(odd="2.15")
    with pytest.raises(TypeError, match="odd must be a number"):
        _snapshot(odd=True)
    with pytest.raises(TypeError, match="source must be a string"):
        _snapshot(source=123)
    with pytest.raises(TypeError, match="observed_at must be a datetime"):
        _snapshot(observed_at="2026-09-14T12:00:00Z")


def test_quote_snapshot_rejects_invalid_odd() -> None:
    with pytest.raises(ValueError, match="greater than 1.0"):
        _snapshot(odd=1.0)
    with pytest.raises(ValueError, match="greater than 1.0"):
        _snapshot(odd=float("nan"))


def test_quote_snapshot_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _snapshot(observed_at=datetime(2026, 9, 14, 12, 0))  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        _snapshot(captured_at=datetime(2026, 9, 14, 12, 0))  # noqa: DTZ001
