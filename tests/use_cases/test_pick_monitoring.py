from datetime import UTC, datetime

from h2h.domain.fixture_identity import ProviderFixtureReference, ResolvedFixtureIdentity
from h2h.domain.odds import Market
from h2h.domain.pick_monitoring import OddsLifecyclePolicy
from h2h.use_cases.pick_monitoring import (
    ReconcileRegisteredPickMonitoring,
    RefreshRegisteredPickOdds,
    StartRegisteredPickMonitoring,
)
from h2h.persistence.pick_monitoring import PickQuoteRefreshTarget


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)
POLICY = OddsLifecyclePolicy(300, 600, 900)


class Repository:
    def __init__(self):
        self.started = []
        self.finalized = []
        self.claim_limits = []
        self.pending = False

    def start(self, pick_id, policy, *, started_at):
        self.started.append((pick_id, policy, started_at))
        return "started"

    def unstarted_pick_ids(self):
        return ("p1", "p2")

    def monitored_pick_ids(self):
        return ()

    def claim_due(self, *, claimed_at, limit):
        self.claim_limits.append(limit)
        return ("p1", "p2")

    def has_due_refreshes(self, *, as_of):
        return self.pending

    def fixture_identities_for_picks(self, pick_ids):
        return (
            ResolvedFixtureIdentity(
                "api-football:42", ProviderFixtureReference("api-football", "42")
            ),
        )


class Source:
    def __init__(self):
        self.calls = 0

    def fetch_quotes(self, *, fixture_identity, market=None):
        self.calls += 1
        return ("quote",)


class Ingestion:
    def ingest(self, quotes):
        assert quotes == ("quote",)
        return 1


def test_start_supplies_pinned_policy_and_utc_time() -> None:
    repository = Repository()
    assert (
        StartRegisteredPickMonitoring(repository, POLICY, clock=lambda: NOW).execute("p1")
        == "started"
    )
    assert repository.started == [("p1", POLICY, NOW)]


def test_refresh_claims_picks_and_groups_one_fixture() -> None:
    repository, source = Repository(), Source()
    result = RefreshRegisteredPickOdds(repository, source, Ingestion(), clock=lambda: NOW).execute()
    assert result.claimed_pick_ids == ("p1", "p2")
    assert result.refreshed_fixture_ids == ("api-football:42",)
    assert result.persisted_snapshot_count == 1
    assert source.calls == 1
    assert repository.claim_limits == [2]
    assert not result.pending_work


def test_refresh_reports_remaining_due_work_for_fair_rescheduling() -> None:
    repository, source = Repository(), Source()
    repository.pending = True

    result = RefreshRegisteredPickOdds(
        repository, source, Ingestion(), clock=lambda: NOW
    ).execute()

    assert result.pending_work


def test_refresh_targets_the_bookmaker_registered_on_each_pick() -> None:
    identity = ResolvedFixtureIdentity(
        "api-football:42", ProviderFixtureReference("api-football", "42")
    )

    class TargetRepository(Repository):
        def quote_refresh_targets_for_picks(self, _pick_ids):
            return (PickQuoteRefreshTarget(identity, 34, Market.BTTS),)

    class TargetSource:
        def __init__(self):
            self.calls = []

        def fetch_quotes(self, *, fixture_identity, bookmaker_id=None, market=None):
            self.calls.append((fixture_identity.fixture_id, bookmaker_id, market))
            return ("quote",)

    source = TargetSource()
    RefreshRegisteredPickOdds(TargetRepository(), source, Ingestion(), clock=lambda: NOW).execute()

    assert source.calls == [("api-football:42", 34, Market.BTTS)]


def test_reconciliation_starts_every_unstarted_registered_pick() -> None:
    repository = Repository()
    result = ReconcileRegisteredPickMonitoring(repository, POLICY, clock=lambda: NOW).execute()
    assert result.started_pick_ids == ("p1", "p2")
    assert [call[0] for call in repository.started] == ["p1", "p2"]
