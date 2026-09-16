from datetime import UTC, datetime

from h2h.domain.fixture_identity import ProviderFixtureReference, ResolvedFixtureIdentity
from h2h.domain.pick_monitoring import OddsLifecyclePolicy
from h2h.use_cases.pick_monitoring import (
    ReconcileRegisteredPickMonitoring,
    RefreshRegisteredPickOdds,
    StartRegisteredPickMonitoring,
)


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)
POLICY = OddsLifecyclePolicy(300, 600, 900)


class Repository:
    def __init__(self):
        self.started = []
        self.finalized = []

    def start(self, pick_id, policy, *, started_at):
        self.started.append((pick_id, policy, started_at))
        return "started"

    def unstarted_pick_ids(self):
        return ("p1", "p2")

    def monitored_pick_ids(self):
        return ()

    def claim_due(self, *, claimed_at, limit):
        return ("p1", "p2")

    def fixture_identities_for_picks(self, pick_ids):
        return (
            ResolvedFixtureIdentity(
                "api-football:42", ProviderFixtureReference("api-football", "42")
            ),
        )


class Source:
    def __init__(self):
        self.calls = 0

    def fetch_quotes(self, *, fixture_identity):
        self.calls += 1
        return ("quote",)


class Ingestion:
    def ingest(self, quotes):
        assert quotes == ("quote",)
        return 1


def test_start_supplies_pinned_policy_and_utc_time() -> None:
    repository = Repository()
    assert StartRegisteredPickMonitoring(
        repository, POLICY, clock=lambda: NOW
    ).execute("p1") == "started"
    assert repository.started == [("p1", POLICY, NOW)]


def test_refresh_claims_picks_and_groups_one_fixture() -> None:
    repository, source = Repository(), Source()
    result = RefreshRegisteredPickOdds(
        repository, source, Ingestion(), clock=lambda: NOW
    ).execute()
    assert result.claimed_pick_ids == ("p1", "p2")
    assert result.refreshed_fixture_ids == ("api-football:42",)
    assert result.persisted_snapshot_count == 1
    assert source.calls == 1


def test_reconciliation_starts_every_unstarted_registered_pick() -> None:
    repository = Repository()
    result = ReconcileRegisteredPickMonitoring(
        repository, POLICY, clock=lambda: NOW
    ).execute()
    assert result.started_pick_ids == ("p1", "p2")
    assert [call[0] for call in repository.started] == ["p1", "p2"]
