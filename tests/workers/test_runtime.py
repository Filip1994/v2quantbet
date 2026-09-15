import signal

import pytest

from h2h.workers.runtime import WorkerRuntime, install_shutdown_handlers, run_worker


def test_run_once_executes_job() -> None:
    calls: list[str] = []
    runtime = WorkerRuntime(job=lambda: calls.append("run"))

    runtime.run_once()

    assert calls == ["run"]


def test_run_forever_runs_job_and_sleeps_until_stopped() -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def job() -> None:
        calls.append("run")
        if len(calls) == 2:
            raise KeyboardInterrupt

    runtime = WorkerRuntime(job=job, interval_seconds=15, sleep=sleeps.append)

    with pytest.raises(KeyboardInterrupt):
        runtime.run_forever()

    assert calls == ["run", "run"]
    assert sleeps == [15]


def test_run_forever_stops_cooperatively_before_next_iteration() -> None:
    calls: list[str] = []
    sleeps: list[float] = []
    stop = iter([False, True]).__next__
    runtime = WorkerRuntime(
        job=lambda: calls.append("run"),
        interval_seconds=15,
        sleep=sleeps.append,
        should_stop=stop,
    )

    runtime.run_forever()

    assert calls == ["run"]
    assert sleeps == [15]


def test_run_worker_forwards_shutdown_predicate() -> None:
    calls: list[str] = []
    stop = iter([False, True]).__next__

    run_worker(lambda: calls.append("run"), interval_seconds=5, should_stop=stop)

    assert calls == ["run"]


def test_install_shutdown_handlers_routes_supported_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: dict[signal.Signals, object] = {}
    shutdowns: list[str] = []

    def register(signum: signal.Signals, handler: object) -> object:
        registered[signum] = handler
        return signal.SIG_DFL

    monkeypatch.setattr(signal, "signal", register)
    install_shutdown_handlers(lambda: shutdowns.append("stop"))

    assert set(registered) == {signal.SIGTERM, signal.SIGINT}
    for handler in registered.values():
        handler(signal.SIGTERM, None)  # type: ignore[operator]

    assert shutdowns == ["stop", "stop"]


def test_runtime_rejects_non_positive_interval() -> None:
    with pytest.raises(ValueError, match="positive"):
        WorkerRuntime(job=lambda: None, interval_seconds=0)
