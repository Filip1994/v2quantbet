from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

from h2h.workers.orchestrator import ProductionOrchestrator, ScheduledJob


class RuntimeFake:
    def __init__(self) -> None:
        self.starts: list[tuple[str, datetime]] = []
        self.successes: list[tuple[str, datetime, datetime]] = []

    def worker_started(self, worker, _instance, *, at):
        self.starts.append((worker, at))

    def worker_succeeded(self, worker, _instance, *, at, next_due_at):
        self.successes.append((worker, at, next_due_at))

    def worker_failed(self, *_args, **_kwargs):
        raise AssertionError("unexpected worker failure")


class Stop:
    def __init__(self, now: list[datetime]) -> None:
        self.now = now
        self.stopped = False

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, seconds):
        self.now[0] += timedelta(seconds=seconds)


def test_pending_workers_get_one_turn_per_round_without_starvation() -> None:
    now = [datetime(2026, 9, 22, 12, tzinfo=UTC)]
    stop = Stop(now)
    runtime = RuntimeFake()
    order: list[str] = []
    durations = {"discovery": 2, "opportunity": 3, "monitoring": 1, "results": 1}

    def run(name):
        order.append(name)
        now[0] += timedelta(seconds=durations[name])
        if name == "results" and order.count("results") == 3:
            stop.set()

    jobs = tuple(
        ScheduledJob(
            name,
            60,
            lambda name=name: run(name),
            has_pending_work=lambda: True,
        )
        for name in ("discovery", "opportunity", "monitoring", "results")
    )
    ProductionOrchestrator(
        jobs,
        runtime,
        instance_id="test",
        stop=stop,  # type: ignore[arg-type]
        tick_seconds=1,
        leader_healthy=lambda: True,
        clock=lambda: now[0],
    ).run_forever()

    assert order == ["discovery", "opportunity", "monitoring", "results"] * 3
    for worker in durations:
        starts = [at for name, at in runtime.starts if name == worker]
        assert max((right - left).total_seconds() for left, right in pairwise(starts)) < 120


def test_overrun_uses_completion_based_next_due_and_does_not_instantly_rerun() -> None:
    now = [datetime(2026, 9, 22, 12, tzinfo=UTC)]
    start = now[0]
    stop = Stop(now)
    runtime = RuntimeFake()
    runs: list[datetime] = []

    def run():
        runs.append(now[0])
        now[0] += timedelta(seconds=70)
        if len(runs) == 2:
            stop.set()

    ProductionOrchestrator(
        (ScheduledJob("opportunity", 60, run),),
        runtime,
        instance_id="test",
        stop=stop,  # type: ignore[arg-type]
        tick_seconds=5,
        leader_healthy=lambda: True,
        clock=lambda: now[0],
    ).run_forever()

    assert runs == [start, start + timedelta(seconds=130)]
    assert runtime.successes[0][2] == start + timedelta(seconds=130)


def test_pending_worker_can_use_normal_interval_as_backlog_cooldown() -> None:
    now = [datetime(2026, 9, 22, 12, tzinfo=UTC)]
    start = now[0]
    stop = Stop(now)
    runtime = RuntimeFake()
    runs: list[datetime] = []

    def run():
        runs.append(now[0])
        now[0] += timedelta(seconds=10)
        if len(runs) == 2:
            stop.set()

    ProductionOrchestrator(
        (
            ScheduledJob(
                "opportunity",
                60,
                run,
                has_pending_work=lambda: True,
                pending_delay_seconds=60,
            ),
        ),
        runtime,
        instance_id="test",
        stop=stop,  # type: ignore[arg-type]
        tick_seconds=5,
        leader_healthy=lambda: True,
        clock=lambda: now[0],
    ).run_forever()

    assert runs == [start, start + timedelta(seconds=70)]
    assert runtime.successes[0][2] == start + timedelta(seconds=70)


def test_pending_delay_rejects_negative_values() -> None:
    try:
        ScheduledJob("opportunity", 60, lambda: None, pending_delay_seconds=-1)
    except ValueError as exc:
        assert "pending delay" in str(exc)
    else:
        raise AssertionError("negative pending delay must be rejected")
