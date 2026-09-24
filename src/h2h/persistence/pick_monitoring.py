"""Persistence contract and operational errors for pick odds monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from h2h.domain.pick_monitoring import (
    ClosingFinalization,
    MonitoringRecord,
    OddsLifecyclePolicy,
    PickOddsLifecycle,
)
from h2h.domain.fixture_identity import ResolvedFixtureIdentity
from h2h.domain.odds import Market


@dataclass(frozen=True, slots=True)
class PickQuoteRefreshTarget:
    fixture_identity: ResolvedFixtureIdentity
    bookmaker_id: int
    market: Market | None = None


class PickMonitoringConflictError(ValueError):
    """A durable transition or immutable finalization contradicts existing state."""


class PickMonitoringNotStartedError(RuntimeError):
    """The requested operation requires a MONITORING pick."""


class PickClosingNotDueError(RuntimeError):
    """The authoritative fixture cutoff has not yet been reached."""


class PickMonitoringRepository(Protocol):
    def start(
        self, pick_id: str, policy: OddsLifecyclePolicy, *, started_at: datetime
    ) -> MonitoringRecord: ...

    def claim_due(self, *, claimed_at: datetime, limit: int) -> tuple[str, ...]: ...

    def has_due_refreshes(self, *, as_of: datetime) -> bool: ...

    def finalize(self, pick_id: str, *, finalized_at: datetime) -> ClosingFinalization: ...

    def read_lifecycle(self, pick_id: str, *, as_of: datetime) -> PickOddsLifecycle: ...

    def unstarted_pick_ids(self) -> tuple[str, ...]: ...

    def monitored_pick_ids(self) -> tuple[str, ...]: ...

    def fixture_identities_for_picks(
        self, pick_ids: tuple[str, ...]
    ) -> tuple[ResolvedFixtureIdentity, ...]: ...

    def quote_refresh_targets_for_picks(
        self, pick_ids: tuple[str, ...]
    ) -> tuple[PickQuoteRefreshTarget, ...]: ...
