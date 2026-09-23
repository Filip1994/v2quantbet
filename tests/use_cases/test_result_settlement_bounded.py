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
