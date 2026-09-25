"""Bounded quote monitoring for exposure-blocked research signals."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from h2h.use_cases.pick_monitoring import (
    ReconcileRegisteredPickMonitoring,
    ReconciliationResult,
    RefreshRegisteredPickOdds,
    RefreshResult,
)


LOGGER = logging.getLogger("quantbet.research_monitoring")


@dataclass(frozen=True, slots=True)
class ResearchMonitoringCycleResult:
    reconciliation: ReconciliationResult
    refresh: RefreshResult


class ResearchSignalMonitoringWorker:
    """Reuse the quote lifecycle machinery without registering or staking anything."""

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

    def run_once(self) -> ResearchMonitoringCycleResult:
        result = ResearchMonitoringCycleResult(
            self._reconcile.execute(),
            self._refresh.execute(),
        )
        self._has_pending = result.refresh.pending_work
        LOGGER.info(
            "research monitoring cycle outcomes",
            extra={
                "worker": "research_monitoring",
                "claimed_signal_count": len(result.refresh.claimed_pick_ids),
                "refreshed_fixture_count": len(result.refresh.refreshed_fixture_ids),
                "persisted_snapshot_count": result.refresh.persisted_snapshot_count,
                "pending_work": result.refresh.pending_work,
            },
        )
        return result
