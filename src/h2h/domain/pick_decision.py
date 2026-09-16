"""Immutable eligibility, risk, stake, decision, and registration facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from h2h.domain.odds import Market, Selection


class EligibilityRejectionCode(StrEnum):
    MARKET_SELECTION_NOT_ALLOWED = "MARKET_SELECTION_NOT_ALLOWED"
    BOOKMAKER_NOT_ALLOWED = "BOOKMAKER_NOT_ALLOWED"
    DEVIG_METHOD_NOT_ALLOWED = "DEVIG_METHOD_NOT_ALLOWED"
    EDGE_BELOW_MINIMUM = "EDGE_BELOW_MINIMUM"
    EXPECTED_VALUE_BELOW_MINIMUM = "EXPECTED_VALUE_BELOW_MINIMUM"
    ODDS_BELOW_MINIMUM = "ODDS_BELOW_MINIMUM"
    ODDS_ABOVE_MAXIMUM = "ODDS_ABOVE_MAXIMUM"
    QUOTE_NOT_YET_AVAILABLE = "QUOTE_NOT_YET_AVAILABLE"
    QUOTE_TOO_OLD = "QUOTE_TOO_OLD"
    QUOTE_NOT_PREMATCH = "QUOTE_NOT_PREMATCH"
    REGISTRATION_NOT_PREMATCH = "REGISTRATION_NOT_PREMATCH"
    REGISTRATION_TOO_CLOSE_TO_KICKOFF = "REGISTRATION_TOO_CLOSE_TO_KICKOFF"
    FIXTURE_STATUS_NOT_ALLOWED = "FIXTURE_STATUS_NOT_ALLOWED"


class RiskRejectionCode(StrEnum):
    DUPLICATE_FIXTURE_MARKET = "DUPLICATE_FIXTURE_MARKET"
    STAKE_EXCEEDS_PER_PICK_LIMIT = "STAKE_EXCEEDS_PER_PICK_LIMIT"
    INSUFFICIENT_AVAILABLE_BANKROLL = "INSUFFICIENT_AVAILABLE_BANKROLL"
    MAX_OPEN_EXPOSURE_EXCEEDED = "MAX_OPEN_EXPOSURE_EXCEEDED"


class DecisionOutcome(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RejectionStage(StrEnum):
    ELIGIBILITY = "ELIGIBILITY"
    RISK = "RISK"


class PickLifecycleState(StrEnum):
    REGISTERED = "REGISTERED"


@dataclass(frozen=True, slots=True)
class FixedStakeDecision:
    amount_minor: int
    currency: str
    policy_version: str = "FIXED_STAKE_V1"

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise TypeError("amount_minor must be an integer")
        if self.amount_minor <= 0:
            raise ValueError("amount_minor must be positive")
        if not isinstance(self.currency, str) or len(self.currency) != 3:
            raise ValueError("currency must be a three-letter code")
        if self.policy_version != "FIXED_STAKE_V1":
            raise ValueError("unsupported stake policy version")


@dataclass(frozen=True, slots=True)
class BankrollRiskSnapshot:
    bankroll_account_id: str
    reference_ledger_entry_id: str
    balance_before_minor: int
    open_exposure_before_minor: int
    max_stake_per_pick_minor: int
    max_open_exposure_minor: int

    def __post_init__(self) -> None:
        for name in ("bankroll_account_id", "reference_ledger_entry_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be blank")
        for name in (
            "balance_before_minor",
            "open_exposure_before_minor",
            "max_stake_per_pick_minor",
            "max_open_exposure_minor",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class PickDecision:
    decision_id: str
    registration_request_id: str
    evaluation_id: str
    fixture_observation_id: str
    policy_config_fingerprint: str
    decided_at: datetime
    outcome: DecisionOutcome
    rejection_stage: RejectionStage | None
    reason_codes: tuple[str, ...]
    stake: FixedStakeDecision | None = None
    risk_snapshot: BankrollRiskSnapshot | None = None

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "registration_request_id",
            "evaluation_id",
            "fixture_observation_id",
            "policy_config_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be blank")
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("decided_at must be timezone-aware")
        object.__setattr__(self, "decided_at", self.decided_at.astimezone(UTC))
        if self.outcome is DecisionOutcome.APPROVED:
            if self.rejection_stage is not None or self.reason_codes:
                raise ValueError("approved decision cannot contain rejection reasons")
            if self.stake is None or self.risk_snapshot is None:
                raise ValueError("approved decision requires stake and risk snapshot")
        else:
            if self.rejection_stage is None or not self.reason_codes:
                raise ValueError("rejected decision requires stage and reason codes")
            if self.rejection_stage is RejectionStage.ELIGIBILITY:
                if self.stake is not None or self.risk_snapshot is not None:
                    raise ValueError("eligibility rejection cannot contain risk state")
            elif self.stake is None or self.risk_snapshot is None:
                raise ValueError("risk rejection requires stake and risk snapshot")


@dataclass(frozen=True, slots=True)
class RegisteredPick:
    pick_id: str
    decision_id: str
    evaluation_id: str
    fixture_id: str
    market: Market
    selection: Selection
    entry_snapshot_id: str
    registered_at: datetime
    stake_minor: int
    currency: str
    bankroll_account_id: str
    policy_config_fingerprint: str
    initial_state: PickLifecycleState = PickLifecycleState.REGISTERED

    def __post_init__(self) -> None:
        for name in (
            "pick_id",
            "decision_id",
            "evaluation_id",
            "fixture_id",
            "entry_snapshot_id",
            "currency",
            "bankroll_account_id",
            "policy_config_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be blank")
        if not isinstance(self.market, Market) or not isinstance(self.selection, Selection):
            raise TypeError("market and selection must use canonical enums")
        if self.registered_at.tzinfo is None or self.registered_at.utcoffset() is None:
            raise ValueError("registered_at must be timezone-aware")
        object.__setattr__(self, "registered_at", self.registered_at.astimezone(UTC))
        if isinstance(self.stake_minor, bool) or not isinstance(self.stake_minor, int):
            raise TypeError("stake_minor must be an integer")
        if self.stake_minor <= 0:
            raise ValueError("stake_minor must be positive")
        if self.initial_state is not PickLifecycleState.REGISTERED:
            raise ValueError("initial pick state must be REGISTERED")


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    decision: PickDecision
    pick: RegisteredPick | None

    def __post_init__(self) -> None:
        if (self.decision.outcome is DecisionOutcome.APPROVED) != (self.pick is not None):
            raise ValueError("approved decisions require exactly one registered pick")
