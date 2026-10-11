"""PostgreSQL integration coverage for the read-only bankroll audit.

Runs only with QUANTBET_TEST_DATABASE_URL, using the same synthetic fixtures
and cleanup contract as the existing settlement integration tests.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from h2h.domain.operator_pick_state import OperatorPickState
from h2h.persistence.operator_pick_state import PostgreSQLOperatorPickStateRepository
from scripts.financial_ledger_audit import read_report
from tests.integration.test_postgres_task10_integration import _candidate, _cleanup, _policy
from tests.integration.test_postgres_task12_integration import _migrate, _registered


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def test_audit_reads_actual_pending_played_skipped_history() -> None:
    assert DATABASE_URL is not None
    _migrate()
    candidate = _candidate()
    account = f"finance-audit-{uuid4()}"
    pick = _registered(candidate, account)
    initial = _policy(account).initial_bankroll_minor
    operator = PostgreSQLOperatorPickStateRepository(database_url=DATABASE_URL)
    try:
        pending = read_report(DATABASE_URL, account)
        assert pending["operator_state_totals"]["PENDING"]["pick_count"] == 1
        assert pending["operator"]["played_available_bankroll_minor"] == initial
        assert pending["operator"]["played_realized_pnl_minor"] == 0
        assert pending["system"]["effective_realized_pnl_minor"] == 0
        assert pending["system"]["realized_pnl_identity_holds"] is True
        assert pending["ledger"]["entry_count"] == 2
        assert pending["ledger"]["nonadditive_count"] == 0
        assert pending["ledger"]["sequence_gaps"] == 0

        occurred = datetime.now(UTC)
        operator.set_state(
            pick.pick_id,
            OperatorPickState.PLAYED,
            f"financial-audit-played-{uuid4()}",
            occurred_at=occurred,
        )
        played = read_report(DATABASE_URL, account)
        assert played["operator_state_totals"]["PLAYED"]["pick_count"] == 1
        assert played["operator"]["played_available_bankroll_minor"] == initial - pick.stake_minor
        assert played["operator"]["played_realized_pnl_minor"] == 0
        assert played["system"]["ledger_last_balance_minor"] == pending["system"][
            "ledger_last_balance_minor"
        ]

        operator.set_state(
            pick.pick_id,
            OperatorPickState.SKIPPED,
            f"financial-audit-skipped-{uuid4()}",
            occurred_at=occurred + timedelta(seconds=1),
        )
        skipped = read_report(DATABASE_URL, account)
        assert skipped["operator_state_totals"]["SKIPPED"]["pick_count"] == 1
        assert skipped["operator"]["played_available_bankroll_minor"] == initial
        assert skipped["operator"]["played_realized_pnl_minor"] == 0
        assert skipped["system"]["ledger_last_balance_minor"] == played["system"][
            "ledger_last_balance_minor"
        ]
    finally:
        _cleanup(account, (candidate,))
