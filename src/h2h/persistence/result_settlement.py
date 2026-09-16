"""Persistence boundary and errors for Task #12 results and settlement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from h2h.domain.fixture_result import FixtureResultObservation
from h2h.domain.settlement import ClvAvailability, SettlementOutcome


class ResultPersistenceConflictError(ValueError):
    """An immutable result identity or fixture anchor conflicts."""


class ResultNotStableError(RuntimeError):
    """Settlement was requested before a confirmed final result exists."""


class SettlementConflictError(ValueError):
    """A settlement replay contradicts the committed financial fact."""


@dataclass(frozen=True, slots=True)
class SettlementRecord:
    settlement_event_id: str
    pick_id: str
    result_observation_id: str
    outcome: SettlementOutcome
    entry_odd_decimal: Decimal
    stake_minor: int
    gross_return_minor: int
    realized_pnl_minor: int
    ledger_entry_id: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ClvResult:
    status: ClvAvailability
    clv_ppm: int | None = None
    clv_fact_id: str | None = None


class ResultSettlementRepository(Protocol):
    def persist_result(self, result: FixtureResultObservation, *, checked_at: datetime): ...

    def settle_pick(
        self, pick_id: str, result_observation_id: str, *, settled_at: datetime
    ) -> SettlementRecord: ...

    def finalize_clv(self, pick_id: str, *, realized_at: datetime) -> ClvResult: ...
