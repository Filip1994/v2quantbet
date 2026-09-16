"""Backend worker boundary for restart-safe registered-pick monitoring."""

from __future__ import annotations

from dataclasses import dataclass

from h2h.use_cases.pick_monitoring import (
    ReconcileRegisteredPickMonitoring,
    ReconciliationResult,
    RefreshRegisteredPickOdds,
    RefreshResult,
)


@dataclass(frozen=True, slots=True)
class MonitoringCycleResult:
    reconciliation: ReconciliationResult
    refresh: RefreshResult


class RegisteredPickMonitoringWorker:
    """Reconcile PostgreSQL state first, then refresh durably claimed picks."""

    def __init__(
        self,
        reconcile: ReconcileRegisteredPickMonitoring,
        refresh: RefreshRegisteredPickOdds,
    ) -> None:
        self._reconcile = reconcile
        self._refresh = refresh

    def run_once(self) -> MonitoringCycleResult:
        return MonitoringCycleResult(self._reconcile.execute(), self._refresh.execute())

