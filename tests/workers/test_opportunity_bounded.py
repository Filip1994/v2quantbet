from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.persistence.postgres_runtime import (
    OpportunityCursor,
    OpportunityFixture,
    OpportunitySelection,
)
from h2h.workers.opportunity import OpportunityWorker
from h2h.workers.orchestrator import ProductionOrchestrator, ScheduledJob
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy


class RepositoryFake:
    def __init__(self, fixtures: tuple[OpportunityFixture, ...]) -> None:
        self.fixtures = fixtures
        self.selection_calls: list[tuple[int, OpportunityCursor | None]] = []
        self.failure_batches: list[tuple[tuple[str, str, BaseException, datetime], ...]] = []

    def select_opportunity_fixtures(self, *, item_limit, after, **_kwargs):
        self.selection_calls.append((item_limit, after))
        start = 0
        if after is not None:
            start = next(
                index + 1
                for index, fixture in enumerate(self.fixtures)
                if fixture.fixture_id == after.fixture_id
            )
        batch = self.fixtures[start : start + item_limit]
        end = start + len(batch)
        has_more = end < len(self.fixtures)
        continuation = (
            OpportunityCursor(batch[-1].kickoff_at, batch[-1].fixture_id)
            if has_more and batch
            else None
        )
        return OpportunitySelection(500, 0, 0, 0, batch, continuation, has_more)

    def record_item_failures(self, failures):
        self.failure_batches.append(tuple(failures))

    def clear_item_failure(self, *_args, **_kwargs):
        return None

    def latest_complete_snapshot_ids(self, *_args, **_kwargs):
        return ()


def fixtures(count: int, *, scopes: tuple[tuple[int, int], ...] | None = None):
    now = datetime(2026, 9, 22, 12, tzinfo=UTC)
    scopes = scopes or ((140, 2026),)
    return tuple(
        OpportunityFixture(
            f"api-football:{index:04d}",
            SimpleNamespace(fixture_id=f"api-football:{index:04d}"),
            *scopes[index % len(scopes)],
            now + timedelta(hours=1, seconds=index),
            None,
        )
        for index in range(count)
    )


def worker(repository, ensure_model, **kwargs):
    return OpportunityWorker(
        repository,
        SimpleNamespace(fetch_quotes=lambda **_kwargs: ()),
        SimpleNamespace(ingest=lambda _quotes: 0),
        SimpleNamespace(execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction")),
        SimpleNamespace(),
        SimpleNamespace(),
        bookmaker_id=8,
        allowed_statuses=("NS",),
        ensure_model_available=ensure_model,
        should_stop=kwargs.pop("should_stop", lambda: False),
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=StaleQuoteRetryPolicy(
            timedelta(minutes=2), timedelta(minutes=15), 5, timedelta(hours=1)
        ),
        **kwargs,
    )


def test_opportunity_batch_is_bounded_and_continues_with_keyset_cursor() -> None:
    repository = RepositoryFake(fixtures(25))
    unavailable = lambda _fixture: (_ for _ in ()).throw(
        ActiveModelUnavailableError("missing")
    )
    subject = worker(repository, unavailable, max_items=10)

    cycles = [subject.run_once(), subject.run_once(), subject.run_once()]

    assert [len(cycle.due_fixture_ids) for cycle in cycles] == [10, 10, 5]
    assert [cycle.pending_work for cycle in cycles] == [True, True, False]
    assert [call[0] for call in repository.selection_calls] == [10, 10, 10]
    assert repository.selection_calls[1][1].fixture_id == "api-football:0009"
    assert sum(len(batch) for batch in repository.failure_batches) == 25


def test_wall_budget_advances_cursor_past_examined_normal_fixtures() -> None:
    repository = RepositoryFake(fixtures(6))
    ticks = iter(float(value) for value in range(100))
    subject = worker(
        repository,
        lambda _fixture: None,
        max_items=5,
        max_wall_seconds=2.5,
        monotonic_clock=lambda: next(ticks),
    )

    first = subject.run_once()
    second = subject.run_once()

    assert first.budget_exhausted is True
    assert first.odds_unavailable_fixture_ids == ("api-football:0000",)
    assert repository.selection_calls[0] == (5, None)
    assert repository.selection_calls[1][1] == OpportunityCursor(
        repository.fixtures[0].kickoff_at,
        "api-football:0000",
    )
    assert second.due_fixture_ids[0] == "api-football:0001"


def test_failure_time_is_fresh_for_each_fixture_and_scope_check_is_shared() -> None:
    repository = RepositoryFake(fixtures(2))
    base = datetime(2026, 9, 22, 12, tzinfo=UTC)
    times = iter(base + timedelta(minutes=value) for value in range(5))
    scope_checks: list[str] = []

    def unavailable(fixture):
        scope_checks.append(fixture.fixture_id)
        raise ActiveModelUnavailableError("missing")

    worker(repository, unavailable, clock=lambda: next(times)).run_once()

    failures = repository.failure_batches[0]
    assert scope_checks == ["api-football:0000"]
    assert [failure[3] for failure in failures] == [
        base + timedelta(minutes=2),
        base + timedelta(minutes=4),
    ]


def test_model_unavailability_is_cached_per_scope_but_only_for_one_cycle() -> None:
    repository = RepositoryFake(fixtures(4, scopes=((140, 2026), (39, 2026))))
    available = [False]
    checked: list[tuple[int, int]] = []

    def preflight(fixture):
        checked.append((fixture.league_id, fixture.season))
        if not available[0]:
            raise ActiveModelUnavailableError("missing")

    subject = worker(repository, preflight, max_items=4)
    first = subject.run_once()
    available[0] = True
    second = subject.run_once()

    assert first.model_unavailable_scope_counts == ((140, 2026, 2), (39, 2026, 2))
    assert checked[:2] == [(140, 2026), (39, 2026)]
    assert checked[2:] == [(140, 2026), (39, 2026)]
    assert second.model_unavailable_fixture_ids == ()


def test_future_item_retry_is_observable_and_skips_provider_call() -> None:
    now = datetime(2026, 9, 22, 12, tzinfo=UTC)
    deferred = OpportunityFixture(
        "api-football:retry",
        SimpleNamespace(fixture_id="api-football:retry"),
        140,
        2026,
        now + timedelta(hours=2),
        None,
        next_retry_at=now + timedelta(minutes=30),
    )
    repository = RepositoryFake((deferred,))
    source_calls = []
    subject = OpportunityWorker(
        repository,
        SimpleNamespace(fetch_quotes=lambda **kwargs: source_calls.append(kwargs)),
        SimpleNamespace(ingest=lambda _quotes: 0),
        SimpleNamespace(execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction")),
        SimpleNamespace(),
        SimpleNamespace(),
        bookmaker_id=8,
        allowed_statuses=("NS",),
        ensure_model_available=lambda _fixture: None,
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=StaleQuoteRetryPolicy(
            timedelta(minutes=2), timedelta(minutes=15), 5, timedelta(hours=1)
        ),
        clock=lambda: now,
    )

    cycle = subject.run_once()

    assert cycle.item_retry_deferred == 1
    assert cycle.processed_fixture_ids == ()
    assert source_calls == []


def test_graceful_shutdown_yields_remaining_bounded_work() -> None:
    repository = RepositoryFake(fixtures(10))
    stopping = [False]

    def unavailable(_fixture):
        stopping[0] = True
        raise ActiveModelUnavailableError("missing")

    cycle = worker(
        repository,
        unavailable,
        max_items=10,
        should_stop=lambda: stopping[0],
    ).run_once()

    assert cycle.failed_fixture_ids == ("api-football:0000",)
    assert cycle.pending_work is True
    assert len(repository.failure_batches[0]) == 1


def test_training_pending_defers_scope_once_and_later_activation_resumes() -> None:
    repository = RepositoryFake(fixtures(2))
    status = ["TRAINING_PENDING"]
    status_checks: list[str] = []
    active_checks: list[str] = []

    def coverage(fixture):
        status_checks.append(fixture.fixture_id)
        return status[0]

    subject = worker(
        repository,
        lambda fixture: active_checks.append(fixture.fixture_id),
        max_items=2,
        model_scope_status=coverage,
    )
    first = subject.run_once()
    status[0] = "ACTIVE"
    second = subject.run_once()

    assert first.model_deferred_fixture_ids == (
        "api-football:0000",
        "api-football:0001",
    )
    assert first.failed_fixture_ids == ()
    assert active_checks == ["api-football:0000"]
    assert len(status_checks) == 2  # one scope lookup in each cycle, never per fixture
    assert second.model_deferred_fixture_ids == ()
    assert second.odds_unavailable_fixture_ids == (
        "api-football:0000",
        "api-football:0001",
    )


def test_five_hundred_missing_models_drain_across_fair_scheduler_slices() -> None:
    repository = RepositoryFake(fixtures(500))
    now = [datetime(2026, 9, 22, 12, tzinfo=UTC)]
    subject = worker(
        repository,
        lambda _fixture: (_ for _ in ()).throw(ActiveModelUnavailableError("missing")),
        max_items=10,
        clock=lambda: now[0],
    )
    runs = {
        name: 0
        for name in ("discovery", "model_lifecycle", "monitoring", "results")
    }

    class Runtime:
        def worker_started(self, *_args, **_kwargs):
            return None

        def worker_succeeded(self, *_args, **_kwargs):
            return None

        def worker_failed(self, *_args, **_kwargs):
            raise AssertionError("unexpected worker failure")

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

        def wait(self, seconds):
            now[0] += timedelta(seconds=seconds)

    stop = Stop()

    def mark(name):
        runs[name] += 1
        if name == "results" and sum(len(batch) for batch in repository.failure_batches) == 500:
            stop.set()

    jobs = (
        ScheduledJob("discovery", 1, lambda: mark("discovery"), has_pending_work=lambda: True),
        ScheduledJob(
            "model_lifecycle",
            60,
            lambda: mark("model_lifecycle"),
        ),
        ScheduledJob(
            "opportunity", 60, subject.run_once, has_pending_work=lambda: subject.has_pending
        ),
        ScheduledJob("monitoring", 1, lambda: mark("monitoring"), has_pending_work=lambda: True),
        ScheduledJob("results", 1, lambda: mark("results"), has_pending_work=lambda: True),
    )
    ProductionOrchestrator(
        jobs,
        Runtime(),  # type: ignore[arg-type]
        instance_id="test",
        stop=stop,  # type: ignore[arg-type]
        tick_seconds=1,
        leader_healthy=lambda: True,
        clock=lambda: now[0],
    ).run_forever()

    assert len(repository.selection_calls) == 50
    assert all(len(batch) == 10 for batch in repository.failure_batches)
    assert runs == {
        "discovery": 50,
        "model_lifecycle": 1,
        "monitoring": 50,
        "results": 50,
    }
    assert subject.has_pending is False


def test_stale_retry_reserves_one_slot_while_normal_cursor_keeps_progressing() -> None:
    all_fixtures = fixtures(500)

    class PriorityRepository(RepositoryFake):
        def select_due_stale_quote_retries(self, **_kwargs):
            stale = all_fixtures[-1]
            return OpportunitySelection(1, 0, 0, 0, (stale,), has_more=True)

    repository = PriorityRepository(all_fixtures)
    subject = worker(
        repository,
        lambda _fixture: (_ for _ in ()).throw(ActiveModelUnavailableError("missing")),
        max_items=10,
    )

    first = subject.run_once()
    second = subject.run_once()

    assert first.due_fixture_ids == ("api-football:0499",) + tuple(
        f"api-football:{index:04d}" for index in range(9)
    )
    assert second.due_fixture_ids == ("api-football:0499",) + tuple(
        f"api-football:{index:04d}" for index in range(9, 18)
    )
    assert repository.selection_calls == [
        (9, None),
        (9, OpportunityCursor(all_fixtures[8].kickoff_at, "api-football:0008")),
    ]
    assert all(len(cycle.due_fixture_ids) == 10 for cycle in (first, second))
