from __future__ import annotations

from datetime import UTC, datetime

from h2h.domain.fixture_identity import ProviderFixtureReference, ResolvedFixtureIdentity
from h2h.persistence.postgres_research_signals import ResearchCloseRefreshTarget
from h2h.workers.research_closing import ResearchClosingWorker


NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


class Repository:
    def __init__(self):
        self.finished = []

    def claim_due_close_targets(self, **kwargs):
        self.claim_kwargs = kwargs
        return (
            ResearchCloseRefreshTarget(
                ResolvedFixtureIdentity(
                    "api-football:1577950",
                    ProviderFixtureReference("api-football", "1577950"),
                ),
                8,
            ),
        )

    def finish_close_refresh(self, target, **kwargs):
        self.finished.append((target, kwargs))


class Source:
    def __init__(self):
        self.calls = []

    def fetch_quotes(self, **kwargs):
        self.calls.append(kwargs)
        return ("quote-a", "quote-b")


class Ingestion:
    def __init__(self):
        self.seen = []

    def ingest(self, quotes):
        self.seen.append(quotes)
        return 2


def test_research_close_refresh_is_bounded_by_fixture_and_bookmaker():
    repository = Repository()
    source = Source()
    ingestion = Ingestion()
    worker = ResearchClosingWorker(
        repository,
        source,
        ingestion,
        clock=lambda: NOW,
        window_seconds=900,
        allowed_statuses=("NS",),
    )

    result = worker.run_once()

    assert result.claimed_target_count == 1
    assert result.refreshed_fixture_count == 1
    assert result.persisted_snapshot_count == 2
    assert result.failed_target_count == 0
    assert repository.claim_kwargs["window_seconds"] == 900
    assert repository.claim_kwargs["refresh_interval_seconds"] == 300
    assert repository.claim_kwargs["limit"] == 5
    assert len(source.calls) == 1
    assert source.calls[0]["bookmaker_id"] == 8
    assert "market" not in source.calls[0]
    assert repository.finished[0][1]["outcome"] == "SUCCESS"
    assert repository.finished[0][1]["persisted_snapshot_count"] == 2


def test_research_close_refresh_records_empty_provider_response_without_failure():
    repository = Repository()
    source = Source()
    source.fetch_quotes = lambda **_kwargs: ()
    worker = ResearchClosingWorker(
        repository,
        source,
        Ingestion(),
        clock=lambda: NOW,
        window_seconds=900,
        allowed_statuses=("NS",),
    )

    result = worker.run_once()

    assert result.failed_target_count == 0
    assert repository.finished[0][1]["outcome"] == "NO_QUOTES"
