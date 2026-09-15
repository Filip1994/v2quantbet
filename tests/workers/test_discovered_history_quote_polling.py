from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, call

from h2h.domain.fixture import Fixture
from h2h.workers.discovered_history_quote_polling import DiscoveredHistoryQuotePollingJob


def fixture(provider_fixture_id: str | None, *, kickoff_at: datetime | None = None) -> Fixture:
    return Fixture(
        fixture_id=f"api-football:{provider_fixture_id or 'missing'}",
        home_team="Home FC",
        away_team="Away FC",
        competition_id=39,
        competition_name="Premier League",
        country="England",
        kickoff_at=kickoff_at or datetime(2026, 9, 15, 18, tzinfo=UTC),
        provider="api-football",
        provider_fixture_id=provider_fixture_id,
    )


def test_discovers_and_polls_unique_provider_fixture_ids() -> None:
    discovery = Mock()
    discovery.discover.return_value = [fixture("42"), fixture("42"), fixture("7")]
    source = Mock()
    source.fetch_quotes.side_effect = [(), ()]
    ingestion = Mock()
    ingestion.ingest.side_effect = [3, 5]
    clock = lambda: datetime(2026, 9, 15, 12, tzinfo=UTC)

    job = DiscoveredHistoryQuotePollingJob(
        source,
        ingestion,
        discovery,
        clock=clock,
        lookahead=timedelta(hours=24),
    )

    assert job.run_once() == 8
    discovery.discover.assert_called_once_with(
        datetime(2026, 9, 15, 12, tzinfo=UTC),
        datetime(2026, 9, 16, 12, tzinfo=UTC),
    )
    assert source.fetch_quotes.call_args_list == [
        call(fixture_id=42),
        call(fixture_id=7),
    ]


def test_does_not_refresh_known_fixture_before_next_due_time() -> None:
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    discovery = Mock()
    discovery.discover.return_value = [
        fixture("42", kickoff_at=datetime(2026, 9, 17, 12, tzinfo=UTC))
    ]
    source = Mock()
    source.fetch_quotes.return_value = ()
    ingestion = Mock()
    ingestion.ingest.return_value = 1
    current_time = [now]
    job = DiscoveredHistoryQuotePollingJob(
        source,
        ingestion,
        discovery,
        clock=lambda: current_time[0],
    )

    assert job.run_once() == 1
    current_time[0] = now + timedelta(hours=1)
    assert job.run_once() == 0
    assert source.fetch_quotes.call_count == 1


def test_continues_after_fixture_failure() -> None:
    discovery = Mock()
    discovery.discover.return_value = [fixture("42"), fixture("7")]
    source = Mock()
    source.fetch_quotes.side_effect = [RuntimeError("provider unavailable"), ()]
    ingestion = Mock()
    ingestion.ingest.return_value = 5

    job = DiscoveredHistoryQuotePollingJob(
        source,
        ingestion,
        discovery,
        clock=lambda: datetime(2026, 9, 15, 12, tzinfo=UTC),
    )

    assert job.run_once() == 5
    assert source.fetch_quotes.call_args_list == [
        call(fixture_id=42),
        call(fixture_id=7),
    ]
    ingestion.ingest.assert_called_once_with(())


def test_returns_zero_when_discovery_fails() -> None:
    discovery = Mock()
    discovery.discover.side_effect = RuntimeError("provider unavailable")
    source = Mock()
    ingestion = Mock()

    job = DiscoveredHistoryQuotePollingJob(
        source,
        ingestion,
        discovery,
        clock=lambda: datetime(2026, 9, 15, 12, tzinfo=UTC),
    )

    assert job.run_once() == 0
    source.fetch_quotes.assert_not_called()
    ingestion.ingest.assert_not_called()


def test_ignores_missing_or_invalid_provider_fixture_ids() -> None:
    discovery = Mock()
    discovery.discover.return_value = [fixture(None), fixture("not-an-int"), fixture("0")]
    source = Mock()
    ingestion = Mock()

    job = DiscoveredHistoryQuotePollingJob(
        source,
        ingestion,
        discovery,
        clock=lambda: datetime(2026, 9, 15, 12, tzinfo=UTC),
    )

    assert job.run_once() == 0
    source.fetch_quotes.assert_not_called()
    ingestion.ingest.assert_not_called()


def test_requires_timezone_aware_clock() -> None:
    naive_now = datetime(2026, 9, 15, 12, tzinfo=UTC).replace(tzinfo=None)
    job = DiscoveredHistoryQuotePollingJob(
        Mock(),
        Mock(),
        Mock(),
        clock=lambda: naive_now,
    )

    try:
        job.run_once()
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected timezone validation")
