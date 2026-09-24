from dataclasses import replace

from h2h.domain.pick_decision import BankrollRiskSnapshot, RiskRejectionCode
from h2h.risk.pick_risk import evaluate_risk, fixed_stake
from tests.domain.test_task10_policy import policy


def snapshot(**changes):
    values = {
        "bankroll_account_id": "pilot-rsd",
        "reference_ledger_entry_id": "bankroll-entry-v1:" + "a" * 64,
        "balance_before_minor": 3_000_000,
        "open_exposure_before_minor": 0,
        "max_stake_per_pick_minor": 30_000,
        "max_open_exposure_minor": 300_000,
    }
    values.update(changes)
    return BankrollRiskSnapshot(**values)


def test_fixed_stake_is_exact_minor_units_without_rounding() -> None:
    stake = fixed_stake(policy())
    assert (stake.amount_minor, stake.currency, stake.policy_version) == (
        30_000,
        "RSD",
        "FIXED_STAKE_V1",
    )


def test_risk_boundaries_are_inclusive() -> None:
    stake = fixed_stake(policy())
    assert (
        evaluate_risk(
            stake,
            snapshot(balance_before_minor=30_000, open_exposure_before_minor=270_000),
            duplicate_fixture=False,
        )
        == ()
    )


def test_risk_collects_deterministic_reasons() -> None:
    stake = fixed_stake(replace(policy(), fixed_stake_minor=30_001))
    result = evaluate_risk(
        stake,
        snapshot(balance_before_minor=30_000, open_exposure_before_minor=300_000),
        duplicate_fixture=True,
    )
    assert result == tuple(RiskRejectionCode)
