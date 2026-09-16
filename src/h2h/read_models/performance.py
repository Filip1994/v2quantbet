"""Read-only Task #12 bankroll and performance projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BankrollCurvePoint:
    account_sequence: int
    occurred_at: datetime
    available_minor: int
    open_exposure_minor: int
    equity_at_cost_minor: int


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    bankroll_account_id: str
    currency: str
    available_bankroll_minor: int
    open_exposure_minor: int
    equity_at_cost_minor: int
    realized_pnl_minor: int
    resolved_stake_minor: int
    graded_stake_minor: int
    void_stake_minor: int
    pending_stake_minor: int
    realized_roi: Decimal | None
    win_count: int
    loss_count: int
    void_count: int
    pending_count: int
    clv_count: int
    positive_clv_count: int
    zero_clv_count: int
    negative_clv_count: int
    mean_clv_ppm: Decimal | None
    curve: tuple[BankrollCurvePoint, ...]


@dataclass(frozen=True, slots=True)
class PerformanceGroup:
    league_id: int
    market: str
    model_version_id: str
    settlement_date: object
    pick_count: int
    graded_stake_minor: int
    realized_pnl_minor: int
    mean_clv_ppm: Decimal | None
