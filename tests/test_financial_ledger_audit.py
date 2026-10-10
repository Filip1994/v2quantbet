"""Offline regression coverage for aggregate read-only finance audit."""

from __future__ import annotations

import re

import pytest

from scripts.financial_ledger_audit import (
    ACCOUNT_SQL,
    LEDGER_SQL,
    STATE_SQL,
    build_report,
)


def _state(
    name: str,
    *,
    staked: int,
    settled: int,
    gross: int,
    pnl: int,
) -> dict[str, object]:
    return {
        "operator_state": name,
        "pick_count": 1,
        "staked_minor": staked,
        "pending_stake_minor": staked - settled,
        "settled_stake_minor": settled,
        "gross_return_minor": gross,
        "realized_pnl_minor": pnl,
    }


def _ledger(
    entry_type: str,
    state: str,
    *,
    count: int,
    mismatches: int = 0,
    missing_sequence: int = 0,
) -> dict[str, object]:
    return {
        "entry_type": entry_type,
        "operator_state": state,
        "entry_count": count,
        "nonadditive_count": mismatches,
        "absolute_gap_minor": mismatches * 10_000,
        "sequence_gaps": missing_sequence,
    }


ACCOUNT = {
    "bankroll_account_id": "synthetic-rsd",
    "currency": "RSD",
    "initial_minor": 3_000_000,
    "ledger_last_minor": 2_882_700,
}


def test_audit_separates_skipped_pending_and_played_from_system_pnl() -> None:
    result = build_report(
        ACCOUNT,
        [
            _state("PLAYED", staked=100_000, settled=100_000, gross=160_000, pnl=60_000),
            _state("SKIPPED", staked=30_000, settled=0, gross=0, pnl=0),
            _state("PENDING", staked=10_000, settled=0, gross=0, pnl=0),
        ],
        [
            _ledger("INITIAL_BANKROLL", "NONE", count=1),
            _ledger("STAKE_RESERVED", "PLAYED", count=1),
            _ledger("STAKE_RESERVED", "SKIPPED", count=538, mismatches=538),
            _ledger("STAKE_RESERVED", "PENDING", count=1),
        ],
    )
    assert result["system"]["effective_realized_pnl_minor"] == 60_000
    assert result["system"]["realized_pnl_identity_holds"] is True
    assert result["system"]["ledger_last_balance_minor"] == 2_882_700
    assert result["operator"]["played_realized_pnl_minor"] == 60_000
    assert result["operator"]["played_available_bankroll_minor"] == 3_060_000
    assert result["operator"]["operator_vs_ledger_is_not_an_invariant"] is True
    assert result["operator_state_totals"]["SKIPPED"]["pending_stake_minor"] == 30_000
    assert result["operator_state_totals"]["PENDING"]["pending_stake_minor"] == 10_000
    assert result["ledger"]["nonadditive_count"] == 538
    assert result["ledger"]["other_than_skipped_reservation_count"] == 0
    assert result["ledger"]["sequence_gaps"] == 0
    assert "pick_id" not in str(result)


def test_audit_surfaces_non_skipped_discrepancy_and_invalid_pnl_identity() -> None:
    result = build_report(
        ACCOUNT,
        [_state("PLAYED", staked=100_000, settled=100_000, gross=160_000, pnl=59_000)],
        [_ledger("PAYOUT", "PLAYED", count=1, mismatches=1, missing_sequence=2)],
    )
    assert result["system"]["realized_pnl_identity_holds"] is False
    assert result["ledger"]["other_than_skipped_reservation_count"] == 1
    assert result["ledger"]["sequence_gaps"] == 2


@pytest.mark.parametrize(
    "missing_field",
    ["initial_minor", "ledger_last_minor"],
)
def test_audit_rejects_incomplete_account(missing_field: str) -> None:
    account = {**ACCOUNT, missing_field: None}
    with pytest.raises(ValueError, match="initial ledger"):
        build_report(account, [], [])


def test_all_sql_is_parameterized_select_only_and_audits_correct_chains() -> None:
    for query in (ACCOUNT_SQL, STATE_SQL, LEDGER_SQL):
        assert query.count("%s") == 1
        assert not re.search(
            r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|CREATE|GRANT|REVOKE)\b",
            query,
            re.IGNORECASE,
        )
    assert "prior_event_id = e.settlement_event_id" in STATE_SQL
    assert "occurred_at DESC, persisted_at DESC, event_id DESC" in STATE_SQL
    assert "LAG(l.balance_after_minor)" in LEDGER_SQL
    assert "LAG(l.account_sequence)" in LEDGER_SQL
    assert "STAKE_RESERVED" not in STATE_SQL
