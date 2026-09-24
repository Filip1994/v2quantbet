"""Deterministic fixed-stake and bounded exposure policy."""

from __future__ import annotations

from h2h.domain.pick_decision import (
    BankrollRiskSnapshot,
    FixedStakeDecision,
    RiskRejectionCode,
)
from h2h.domain.registration_policy import RegistrationPolicyConfig


def fixed_stake(policy: RegistrationPolicyConfig) -> FixedStakeDecision:
    return FixedStakeDecision(policy.fixed_stake_minor, policy.currency)


def evaluate_risk(
    stake: FixedStakeDecision,
    snapshot: BankrollRiskSnapshot,
    *,
    duplicate_fixture: bool,
) -> tuple[RiskRejectionCode, ...]:
    failures: set[RiskRejectionCode] = set()
    if duplicate_fixture:
        failures.add(RiskRejectionCode.DUPLICATE_FIXTURE)
    if stake.amount_minor > snapshot.max_stake_per_pick_minor:
        failures.add(RiskRejectionCode.STAKE_EXCEEDS_PER_PICK_LIMIT)
    if stake.amount_minor > snapshot.balance_before_minor:
        failures.add(RiskRejectionCode.INSUFFICIENT_AVAILABLE_BANKROLL)
    if snapshot.open_exposure_before_minor + stake.amount_minor > snapshot.max_open_exposure_minor:
        failures.add(RiskRejectionCode.MAX_OPEN_EXPOSURE_EXCEEDED)
    return tuple(code for code in RiskRejectionCode if code in failures)
