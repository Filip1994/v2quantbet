"""Backend worker boundary for restart-safe registered-pick monitoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass

LOGGER = logging.getLogger("quantbet.monitoring")

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
        self._has_pending = False

    @property
    def has_pending(self) -> bool:
        return self._has_pending

    def run_once(self) -> MonitoringCycleResult:
        result = MonitoringCycleResult(self._reconcile.execute(), self._refresh.execute())
        self._has_pending = result.refresh.pending_work
        LOGGER.info(
            "monitoring cycle outcomes",
            extra={
                "worker": "monitoring",
                "claimed_pick_count": len(result.refresh.claimed_pick_ids),
                "refreshed_fixture_count": len(result.refresh.refreshed_fixture_ids),
                "persisted_snapshot_count": result.refresh.persisted_snapshot_count,
                "pending_work": result.refresh.pending_work,
            },
        )
        return result

