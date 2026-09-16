"""Deterministic settlement, exact minor-unit money and realized CLV."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Final

from h2h.domain.fixture_result import FixtureResultObservation, ResultClassification
from h2h.domain.odds import Market, Selection


SETTLEMENT_RULE_VERSION: Final = "SETTLEMENT_OU25_BTTS_REGULATION_V1"
MONEY_ROUNDING_VERSION: Final = "MONEY_HALF_UP_V1"
CLV_METHOD_VERSION: Final = "CLV_ODDS_RATIO_PPM_V1"
BIGINT_MIN: Final = -(2**63)
BIGINT_MAX: Final = 2**63 - 1


class SettlementOutcome(StrEnum):
    WIN = "WIN"
    LOSS = "LOSS"
    VOID = "VOID"


class SettlementEventKind(StrEnum):
    NORMAL = "NORMAL"
    CORRECTION = "CORRECTION"
    REVERSAL = "REVERSAL"


class ClvAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PENDING_SETTLEMENT = "PENDING_SETTLEMENT"
    NO_VALID_CLOSING = "NO_VALID_CLOSING"
    STALE_CLOSING = "STALE_CLOSING"
    KICKOFF_CHANGED_AFTER_CLOSING = "KICKOFF_CHANGED_AFTER_CLOSING"
    PROVENANCE_CONFLICT = "PROVENANCE_CONFLICT"


@dataclass(frozen=True, slots=True)
class ResultSettlementPolicy:
    initial_delay_seconds: int = 6300
    poll_interval_seconds: int = 300
    suspended_poll_interval_seconds: int = 900
    postponed_poll_interval_seconds: int = 21600
    finality_delay_seconds: int = 900
    claim_lease_seconds: int = 120
    claim_limit: int = 100
    correction_window_seconds: int = 259200

    def __post_init__(self) -> None:
        for name in (
            "initial_delay_seconds",
            "poll_interval_seconds",
            "suspended_poll_interval_seconds",
            "postponed_poll_interval_seconds",
            "finality_delay_seconds",
            "claim_lease_seconds",
            "claim_limit",
            "correction_window_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def finality_delay(self) -> timedelta:
        return timedelta(seconds=self.finality_delay_seconds)


@dataclass(frozen=True, slots=True)
class SettlementAmounts:
    outcome: SettlementOutcome
    stake_minor: int
    entry_odd_decimal: Decimal
    gross_return_minor: int
    realized_pnl_minor: int
    ledger_entry_type: str
    ledger_delta_minor: int


def settle_market(
    market: Market,
    selection: Selection,
    result: FixtureResultObservation,
) -> SettlementOutcome:
    if result.classification is ResultClassification.NON_PLAYED_VOIDABLE:
        return SettlementOutcome.VOID
    if result.classification is not ResultClassification.PLAYED_SETTLEABLE:
        raise ValueError("result is not safely settleable")
    home, away = result.regulation_goals
    if home is None or away is None:
        raise ValueError("settleable result lacks regulation goals")
    total = home + away
    if market is Market.OU_25 and selection is Selection.OVER:
        won = total >= 3
    elif market is Market.OU_25 and selection is Selection.UNDER:
        won = total <= 2
    elif market is Market.BTTS and selection is Selection.YES:
        won = home >= 1 and away >= 1
    elif market is Market.BTTS and selection is Selection.NO:
        won = home == 0 or away == 0
    else:
        raise ValueError("unsupported market/selection")
    return SettlementOutcome.WIN if won else SettlementOutcome.LOSS


def settlement_amounts(
    *, stake_minor: int, entry_odd_decimal: Decimal, outcome: SettlementOutcome
) -> SettlementAmounts:
    if isinstance(stake_minor, bool) or not isinstance(stake_minor, int) or stake_minor <= 0:
        raise ValueError("stake_minor must be positive")
    odd = Decimal(entry_odd_decimal)
    if not odd.is_finite() or odd <= 1:
        raise ValueError("entry odd must be finite and greater than one")
    if outcome is SettlementOutcome.WIN:
        gross = int((Decimal(stake_minor) * odd).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        pnl = gross - stake_minor
        entry_type = "PAYOUT"
        delta = gross
    elif outcome is SettlementOutcome.LOSS:
        gross, pnl, entry_type, delta = 0, -stake_minor, "LOSS", 0
    else:
        gross, pnl, entry_type, delta = stake_minor, 0, "VOID_REFUND", stake_minor
    for value in (gross, pnl, delta):
        if not BIGINT_MIN <= value <= BIGINT_MAX:
            raise OverflowError("settlement amount exceeds PostgreSQL BIGINT")
    return SettlementAmounts(outcome, stake_minor, odd, gross, pnl, entry_type, delta)


def realized_clv_ppm(entry: Decimal, closing: Decimal) -> int:
    entry_value, closing_value = Decimal(entry), Decimal(closing)
    if (
        not entry_value.is_finite()
        or not closing_value.is_finite()
        or entry_value <= 1
        or closing_value <= 1
    ):
        raise ValueError("Entry and Closing odds must be finite and greater than one")
    value = ((entry_value / closing_value) - Decimal(1)) * Decimal(1_000_000)
    result = int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if not BIGINT_MIN <= result <= BIGINT_MAX:
        raise OverflowError("CLV exceeds PostgreSQL BIGINT")
    return result
