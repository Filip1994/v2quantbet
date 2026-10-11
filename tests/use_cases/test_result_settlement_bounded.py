from datetime import UTC, datetime
from types import SimpleNamespace

from h2h.use_cases.result_settlement import ReconcileFixtureResults
from h2h.workers.result_settlement import ResultSettlementWorker


NOW = datetime(2026, 9, 24, tzinfo=UTC)


class Repository:
    def __init__(self) -> None:
        self.claim_limits: list[int | None] = []
        self.pending = True

    def reconcile(self, *, reconciled_at):
        assert reconciled_at == NOW
        return ()

    def claim_due(self, *, claimed_at, limit=None):
        assert claimed_at == NOW
        self.claim_limits.append(limit)
        return ("fixture-1", "fixture-2")

    def provider_contexts(self, fixture_ids):
        assert fixture_ids == ("fixture-1", "fixture-2")
        return ()

    def has_due_results(self, *, as_of):
        assert as_of == NOW
        return self.pending


class Source:
    def fetch(self, _contexts):
        raise AssertionError("no provider call expected without provider contexts")


def test_result_reconciliation_uses_small_bounded_slice_and_reports_pending() -> None:
    repository = Repository()
    reconcile = ReconcileFixtureResults(
        repository,  # type: ignore[arg-type]
        Source(),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    cycle = reconcile.execute()

    assert repository.claim_limits == [2]
    assert cycle.claimed_fixture_ids == ("fixture-1", "fixture-2")
    assert cycle.pending_work
    assert reconcile.has_pending


def test_result_worker_exposes_reconciliation_pending_state() -> None:
    reconcile = SimpleNamespace(has_pending=True, execute=lambda: "cycle")
    worker = ResultSettlementWorker(reconcile)  # type: ignore[arg-type]

    assert worker.has_pending
    assert worker.run_once() == "cycle"


def test_fixture_identity_conflict_does_not_stop_other_results() -> None:
    from h2h.persistence.result_settlement import ResultPersistenceConflictError

    class TwoFixtureRepository:
        def __init__(self) -> None:
            self.persisted = []

        def reconcile(self, *, reconciled_at):
            return ()

        def claim_due(self, *, claimed_at, limit=None):
            return ("bad", "good")

        def provider_contexts(self, fixture_ids):
            return (("bad", 101), ("good", 102))

        def persist_result(self, result, *, checked_at):
            if result.fixture_id == "bad":
                raise ResultPersistenceConflictError(
                    "result contradicts durable fixture identity"
                )
            self.persisted.append(result.fixture_id)

        def stable_result(self, fixture_id, *, as_of):
            return None

        def has_due_results(self, *, as_of):
            return False

    class TwoFixtureSource:
        def fetch(self, contexts):
            return {contexts[0][0]: {}}

    repository = TwoFixtureRepository()
    failures = []
    successes = []
    reconcile = ReconcileFixtureResults(
        repository,  # type: ignore[arg-type]
        TwoFixtureSource(),  # type: ignore[arg-type]
        clock=lambda: NOW,
        on_item_failure=lambda fixture_id, error, at: failures.append(
            (fixture_id, type(error), at)
        ),
        on_item_success=successes.append,
    )
    reconcile._normalizer = SimpleNamespace(
        normalize=lambda payload, *, fixture_id, acquired_at: SimpleNamespace(
            fixture_id=fixture_id
        )
    )

    cycle = reconcile.execute()

    assert repository.persisted == ["good"]
    assert failures == [("bad", ResultPersistenceConflictError, NOW)]
    assert successes == ["good"]
    assert cycle.claimed_fixture_ids == ("bad", "good")
    assert not cycle.pending_work
