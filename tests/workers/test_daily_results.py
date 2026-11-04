from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from h2h.odds import ApiBudgetExceededError
from h2h.use_cases.result_settlement import ReconcileFixtureResults
from h2h.workers.orchestrator import ProductionOrchestrator, ScheduledJob
from tests.workers.test_scheduler_fairness import RuntimeFake, Stop


def test_daily_results_batch_all_due_fixtures_once_even_when_first_batch_fails():
    now = datetime(2026, 11, 5, 7, tzinfo=UTC)
    fixture_ids = tuple(f"fixture-{n}" for n in range(45))
    claims = []
    fetches = []
    persisted = []
    failures = []
    reconciled = []

    def claim_due(*, claimed_at, limit, fixture_ids):
        claims.append(fixture_ids)
        assert limit == len(fixture_ids)
        return fixture_ids

    def fetch(contexts):
        fetches.append(contexts)
        if len(fetches) == 1:
            raise RuntimeError("provider batch failed")
        return {fixture_id: {} for fixture_id, _ in contexts}

    repository = SimpleNamespace(
        policy=SimpleNamespace(claim_limit=100),
        reconcile=lambda **kwargs: reconciled.append(kwargs) or (),
        due_fixture_ids=lambda **kwargs: fixture_ids,
        claim_due=claim_due,
        provider_contexts=lambda ids: tuple((item, n) for n, item in enumerate(ids)),
        persist_result=lambda result, **kwargs: persisted.append(result.fixture_id),
        stable_result=lambda *args, **kwargs: None,
        has_due_results=lambda **kwargs: True,
    )
    reconcile = ReconcileFixtureResults(
        repository, SimpleNamespace(fetch=fetch), clock=lambda: now,
        on_item_failure=lambda fixture_id, error, at: failures.append(fixture_id),
    )
    reconcile._normalizer = SimpleNamespace(
        normalize=lambda payload, **kwargs: SimpleNamespace(fixture_id=kwargs["fixture_id"])
    )

    cycle = reconcile.execute_daily()

    assert len(reconciled) == 1
    assert [len(batch) for batch in fetches] == [20, 20, 5]
    assert tuple(item for batch in claims for item in batch) == fixture_ids
    assert failures == list(fixture_ids[:20])
    assert persisted == list(fixture_ids[20:])
    assert cycle.persisted_result_count == 25
    assert cycle.claimed_fixture_ids == fixture_ids
    assert not cycle.pending_work


class DailyRuntime(RuntimeFake):
    def __init__(self):
        super().__init__()
        self.last_start = None
        self.scheduled = []
        self.failures = []

    def worker_statuses(self):
        return (SimpleNamespace(worker_name="results", last_started_at=self.last_start),)

    def worker_scheduled(self, worker, instance, *, at, next_due_at):
        self.scheduled.append(next_due_at)

    def worker_started(self, worker, instance, *, at):
        super().worker_started(worker, instance, at=at)
        self.last_start = at

    def worker_failed(self, worker, instance, error, *, at, next_due_at):
        self.failures.append(next_due_at)


@pytest.mark.parametrize("fails", [False, True])
def test_daily_schedule_runs_at_eight_and_does_not_repeat_after_restart(fails):
    now = [datetime(2026, 11, 5, 6, 59, tzinfo=UTC)]
    runtime = DailyRuntime()
    stop = Stop(now)
    runs = []

    def run():
        runs.append(now[0])
        stop.set()
        if fails:
            raise ApiBudgetExceededError("daily limit")

    job = ScheduledJob(
        "results", 86400, run, has_pending_work=lambda: True, daily_at_hour=8
    )
    ProductionOrchestrator(
        (job,), runtime, instance_id="first", stop=stop, tick_seconds=5,
        leader_healthy=lambda: True, clock=lambda: now[0],
    ).run_forever()

    assert runs == [datetime(2026, 11, 5, 7, tzinfo=UTC)]
    assert runtime.scheduled == [runs[0]]
    next_due = runtime.failures[-1] if fails else runtime.successes[-1][2]
    assert next_due == datetime(2026, 11, 6, 7, tzinfo=UTC)

    restarted = ProductionOrchestrator(
        (job,), runtime, instance_id="second", stop=stop, tick_seconds=5,
        leader_healthy=lambda: True, clock=lambda: now[0] + timedelta(hours=1),
    )
    assert restarted._next_due["results"] == next_due


@pytest.mark.parametrize(
    ("start", "next_run", "elapsed_hours"),
    [
        (datetime(2026, 3, 28, 7, tzinfo=UTC), datetime(2026, 3, 29, 6, tzinfo=UTC), 23),
        (datetime(2026, 10, 24, 6, tzinfo=UTC), datetime(2026, 10, 25, 7, tzinfo=UTC), 25),
    ],
)
def test_daily_schedule_stays_at_local_eight_across_clock_changes(start, next_run, elapsed_hours):
    job = ScheduledJob("results", 86400, lambda: None, daily_at_hour=8)
    assert job.next_daily_run(start, previous_start=start) == next_run
    assert (next_run - start).total_seconds() == elapsed_hours * 3600


def test_missed_daily_schedule_catches_up_after_downtime():
    job = ScheduledJob("results", 86400, lambda: None, daily_at_hour=8)
    now = datetime(2026, 11, 5, 12, tzinfo=UTC)
    assert job.next_daily_run(now) == now


@pytest.mark.parametrize("hour", [-1, 24, True, 8.5])
def test_daily_schedule_rejects_invalid_hour(hour):
    with pytest.raises(ValueError, match="daily hour"):
        ScheduledJob("results", 86400, lambda: None, daily_at_hour=hour)
