"""Interruptible independent-cadence scheduler for the single active leader."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event

from h2h.odds import ApiBudgetExceededError
from h2h.odds.http import TransportError
from h2h.persistence.fixtures import FixturePersistenceConflictError
from h2h.persistence.model_lifecycle import ModelPersistenceConflictError
from h2h.persistence.pick_registration import (
    BankrollBootstrapConflictError,
    RegistrationPersistenceConflictError,
    RegistrationProvenanceError,
)
from h2h.persistence.predictions import PredictionPersistenceConflictError
from h2h.persistence.quote_history import QuoteHistoryConflictError
from h2h.persistence.result_settlement import ResultPersistenceConflictError, SettlementConflictError
from h2h.persistence.value_evaluations import ValueEvaluationPersistenceConflictError
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository


LOGGER = logging.getLogger("quantbet.orchestrator")

_INVARIANT_ERRORS = (
    FixturePersistenceConflictError,
    ModelPersistenceConflictError,
    BankrollBootstrapConflictError,
    RegistrationPersistenceConflictError,
    RegistrationProvenanceError,
    PredictionPersistenceConflictError,
    QuoteHistoryConflictError,
    ResultPersistenceConflictError,
    SettlementConflictError,
    ValueEvaluationPersistenceConflictError,
)


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    name: str
    interval_seconds: float
    run: Callable[[], object]
    has_pending_work: Callable[[], bool] = lambda: False
    pending_delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip() or self.interval_seconds <= 0:
            raise ValueError("scheduled job requires a name and positive interval")
        if self.pending_delay_seconds < 0:
            raise ValueError("scheduled job pending delay must be non-negative")


class ProductionOrchestrator:
    def __init__(
        self,
        jobs: tuple[ScheduledJob, ...],
        runtime: PostgreSQLRuntimeRepository,
        *,
        instance_id: str,
        stop: Event,
        tick_seconds: float,
        leader_healthy: Callable[[], bool],
        on_degraded: Callable[[BaseException], None] = lambda _error: None,
        on_recovered: Callable[[], None] = lambda: None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._jobs = jobs
        self._runtime = runtime
        self._instance_id = instance_id
        self._stop = stop
        self._tick_seconds = tick_seconds
        self._leader_healthy = leader_healthy
        self._on_degraded = on_degraded
        self._on_recovered = on_recovered
        self._clock = clock
        self._next_due = {job.name: self._clock() for job in jobs}

    def run_forever(self) -> bool:
        """Return False when leadership is lost, True on requested shutdown."""
        while not self._stop.is_set():
            if not self._leader_healthy():
                return False
            for job in self._jobs:
                if self._stop.is_set():
                    break
                cycle_start = self._clock().astimezone(UTC)
                if cycle_start < self._next_due[job.name]:
                    continue
                try:
                    self._runtime.worker_started(job.name, self._instance_id, at=cycle_start)
                    job.run()
                    finished = self._clock().astimezone(UTC)
                    pending = job.has_pending_work()
                    # Ordinary cadence is completion-based: an overrun cannot make the
                    # same worker instantly due again. Pending bounded work can opt into
                    # a small cooldown; zero preserves eager next-round scheduling.
                    next_due = finished + timedelta(
                        seconds=(
                            job.pending_delay_seconds
                            if pending
                            else job.interval_seconds
                        )
                    )
                    self._runtime.worker_succeeded(
                        job.name, self._instance_id, at=finished, next_due_at=next_due
                    )
                    self._on_recovered()
                    LOGGER.info(
                        "worker cycle succeeded",
                        extra={
                            "worker": job.name,
                            "cycle_started_at": cycle_start,
                            "cycle_finished_at": finished,
                            "duration_seconds": (finished - cycle_start).total_seconds(),
                            "pending_work": pending,
                            "next_due_at": next_due,
                        },
                    )
                except BaseException as exc:
                    if self._fatal(exc):
                        raise
                    self._on_degraded(exc)
                    failed_at = self._clock().astimezone(UTC)
                    next_due = failed_at + timedelta(seconds=job.interval_seconds)
                    if isinstance(exc, ApiBudgetExceededError):
                        tomorrow = failed_at.date() + timedelta(days=1)
                        next_due = datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC)
                    try:
                        self._runtime.worker_failed(
                            job.name,
                            self._instance_id,
                            exc,
                            at=failed_at,
                            next_due_at=next_due,
                        )
                    except Exception:
                        LOGGER.exception("could not persist worker failure", extra={"worker": job.name})
                    LOGGER.warning(
                        "worker cycle deferred",
                        extra={"worker": job.name, "error_class": type(exc).__name__},
                    )
                self._next_due[job.name] = next_due
            self._stop.wait(self._tick_seconds)
        return True

    @staticmethod
    def _fatal(error: BaseException) -> bool:
        if isinstance(error, _INVARIANT_ERRORS):
            return True
        try:
            import psycopg

            if isinstance(error, (psycopg.IntegrityError, psycopg.DataError)):
                return True
            if isinstance(error, (psycopg.OperationalError, psycopg.InterfaceError)):
                return False
        except ImportError:
            pass
        return not isinstance(
            error,
            (ApiBudgetExceededError, TransportError, TypeError, ValueError, RuntimeError),
        )
