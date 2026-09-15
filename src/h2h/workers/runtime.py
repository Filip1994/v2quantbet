"""Small, testable runtime loop for background jobs."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


Job = Callable[[], None]
Sleeper = Callable[[float], None]
StopPredicate = Callable[[], bool]


@dataclass(frozen=True)
class WorkerRuntime:
    """Execute a job repeatedly with an injectable shutdown boundary."""

    job: Job
    interval_seconds: float = 60.0
    sleep: Sleeper = time.sleep
    should_stop: StopPredicate = lambda: False

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

    def run_once(self) -> None:
        """Execute one worker iteration."""
        self.job()

    def run_forever(self) -> None:
        """Run until the shutdown predicate returns true or an external signal stops it."""
        while not self.should_stop():
            self.run_once()
            self.sleep(self.interval_seconds)


def run_worker(job: Job, *, interval_seconds: float = 60.0) -> None:
    """Convenience entrypoint for a production process supervisor."""
    WorkerRuntime(job=job, interval_seconds=interval_seconds).run_forever()
