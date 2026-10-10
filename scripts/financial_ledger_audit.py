"""Read-only QuantBet finance reconciliation; never writes production data.

Usage: DATABASE_URL=... python scripts/financial_ledger_audit.py --account quantbet-pilot-rsd

The report intentionally contains no pick IDs. It distinguishes the immutable
system ledger, effective system settlements and operator PLAYED-only projection.
A nonadditive SKIPPED reservation is a diagnostic, not a fix instruction.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

ACCOUNT_SQL = """
SELECT a.bankroll_account_id, a.currency,
    (SELECT l.amount_minor FROM bankroll_ledger_entries l
     WHERE l.bankroll_account_id = a.bankroll_account_id
       AND l.entry_type = 'INITIAL_BANKROLL'
     ORDER BY l.account_sequence LIMIT 1) AS initial_minor,
    (SELECT l.balance_after_minor FROM bankroll_ledger_entries l
     WHERE l.bankroll_account_id = a.bankroll_account_id
     ORDER BY l.account_sequence DESC LIMIT 1) AS ledger_last_minor
FROM bankroll_accounts a WHERE a.bankroll_account_id = %s
"""

STATE_SQL = """
WITH latest_operator AS (
    SELECT DISTINCT ON (pick_id) pick_id, state
    FROM pick_operator_state_events
    ORDER BY pick_id, occurred_at DESC, persisted_at DESC, event_id DESC
), effective AS (
    SELECT e.* FROM pick_settlement_events e
    WHERE NOT EXISTS (
        SELECT 1 FROM pick_settlement_events successor
        WHERE successor.prior_event_id = e.settlement_event_id
    )
)
SELECT COALESCE(o.state, 'PENDING') AS operator_state,
    COUNT(*) AS pick_count,
    COALESCE(SUM(r.stake_minor), 0) AS staked_minor,
    COALESCE(SUM(r.stake_minor)
        FILTER (WHERE e.outcome IS NULL), 0) AS pending_stake_minor,
    COALESCE(SUM(r.stake_minor)
        FILTER (WHERE e.outcome IS NOT NULL), 0) AS settled_stake_minor,
    COALESCE(SUM(e.gross_return_minor)
        FILTER (WHERE e.outcome IS NOT NULL), 0) AS gross_return_minor,
    COALESCE(SUM(e.realized_pnl_minor)
        FILTER (WHERE e.outcome IS NOT NULL), 0) AS realized_pnl_minor
FROM registered_picks r
LEFT JOIN latest_operator o ON o.pick_id = r.pick_id
LEFT JOIN effective e ON e.pick_id = r.pick_id
WHERE r.bankroll_account_id = %s
GROUP BY COALESCE(o.state, 'PENDING')
ORDER BY operator_state
"""

LEDGER_SQL = """
WITH latest_operator AS (
    SELECT DISTINCT ON (pick_id) pick_id, state
    FROM pick_operator_state_events
    ORDER BY pick_id, occurred_at DESC, persisted_at DESC, event_id DESC
), sequenced AS (
    SELECT l.entry_type,
        CASE WHEN l.pick_id IS NULL THEN 'NONE'
             ELSE COALESCE(o.state, 'PENDING') END AS operator_state,
        l.account_sequence, l.amount_minor, l.balance_after_minor,
        LAG(l.balance_after_minor) OVER (
            ORDER BY l.account_sequence
        ) AS previous_balance,
        LAG(l.account_sequence) OVER (
            ORDER BY l.account_sequence
        ) AS previous_sequence
    FROM bankroll_ledger_entries l
    LEFT JOIN latest_operator o ON o.pick_id = l.pick_id
    WHERE l.bankroll_account_id = %s
), discrepancies AS (
    SELECT entry_type, operator_state,
        balance_after_minor - COALESCE(previous_balance, 0)
            - amount_minor AS arithmetic_delta_minor,
        GREATEST(account_sequence -
            COALESCE(previous_sequence, 0) - 1, 0) AS missing_sequence_count
    FROM sequenced
)
SELECT entry_type, operator_state, COUNT(*) AS entry_count,
    COUNT(*) FILTER (WHERE arithmetic_delta_minor <> 0) AS nonadditive_count,
    COALESCE(SUM(ABS(arithmetic_delta_minor))
        FILTER (WHERE arithmetic_delta_minor <> 0), 0) AS absolute_gap_minor,
    COALESCE(SUM(missing_sequence_count), 0) AS sequence_gaps
FROM discrepancies
GROUP BY entry_type, operator_state
ORDER BY entry_type, operator_state
"""


def _amount(row: Mapping[str, Any], key: str) -> int:
    return int(row[key] or 0)


def build_report(
    account: Mapping[str, Any],
    state_rows: Sequence[Mapping[str, Any]],
    ledger_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build an aggregate report; keep individual picks out of the output."""
    if account["initial_minor"] is None or account["ledger_last_minor"] is None:
        raise ValueError("account lacks an initial ledger entry or current balance")

    states = {
        str(row["operator_state"]): {
            key: _amount(row, key)
            for key in (
                "pick_count",
                "staked_minor",
                "pending_stake_minor",
                "settled_stake_minor",
                "gross_return_minor",
                "realized_pnl_minor",
            )
        }
        for row in state_rows
    }
    played = states.get("PLAYED", {})
    initial = _amount(account, "initial_minor")
    operator_available = (
        initial - played.get("staked_minor", 0)
        + played.get("gross_return_minor", 0)
    )

    ledger_groups = [
        {
            "entry_type": str(row["entry_type"]),
            "operator_state": str(row["operator_state"]),
            "entry_count": _amount(row, "entry_count"),
            "nonadditive_count": _amount(row, "nonadditive_count"),
            "absolute_gap_minor": _amount(row, "absolute_gap_minor"),
            "sequence_gaps": _amount(row, "sequence_gaps"),
        }
        for row in ledger_rows
    ]
    system_pnl = sum(item["realized_pnl_minor"] for item in states.values())
    gross = sum(item["gross_return_minor"] for item in states.values())
    settled_stake = sum(item["settled_stake_minor"] for item in states.values())
    nonadditive = sum(item["nonadditive_count"] for item in ledger_groups)
    sequence_gaps = sum(item["sequence_gaps"] for item in ledger_groups)
    other_nonadditive = sum(
        item["nonadditive_count"]
        for item in ledger_groups
        if not (
            item["entry_type"] == "STAKE_RESERVED"
            and item["operator_state"] == "SKIPPED"
        )
    )

    return {
        "account": str(account["bankroll_account_id"]),
        "currency": str(account["currency"]),
        "units": "currency minor units (RSD: 100 minor = 1 dinar)",
        "system": {
            "effective_realized_pnl_minor": system_pnl,
            "realized_pnl_identity_holds": system_pnl == gross - settled_stake,
            "ledger_last_balance_minor": _amount(account, "ledger_last_minor"),
        },
        "operator": {
            "played_realized_pnl_minor": played.get("realized_pnl_minor", 0),
            "played_available_bankroll_minor": operator_available,
            "played_available_is_derived": True,
            "operator_vs_ledger_is_not_an_invariant": True,
        },
        "operator_state_totals": states,
        "ledger": {
            "entry_count": sum(item["entry_count"] for item in ledger_groups),
            "nonadditive_count": nonadditive,
            "other_than_skipped_reservation_count": other_nonadditive,
            "sequence_gaps": sequence_gaps,
            "groups": ledger_groups,
        },
        "notes": [
            "Never use the last system ledger balance as operator PLAYED bankroll.",
            "SKIPPED ledger nonadditivity must be reviewed, not rewritten.",
            "The report is a snapshot only; no historic settlement is modified.",
        ],
    }


def read_report(database_url: str, account_id: str) -> dict[str, Any]:
    """Use a single consistent PostgreSQL read-only transaction."""
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(
        database_url,
        autocommit=True,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on -c statement_timeout=30000",
    ) as connection:
        with connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            with connection.cursor() as cursor:
                cursor.execute(ACCOUNT_SQL, (account_id,))
                account = cursor.fetchone()
                if account is None:
                    raise LookupError("bankroll account does not exist")
                cursor.execute(STATE_SQL, (account_id,))
                state_rows = cursor.fetchall()
                cursor.execute(LEDGER_SQL, (account_id,))
                ledger_rows = cursor.fetchall()
                return build_report(account, state_rows, ledger_rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate, read-only production bankroll reconciliation"
    )
    parser.add_argument("--account", required=True, help="Existing bankroll account")
    arguments = parser.parse_args()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL must be configured locally (never print it)")
    report = read_report(database_url, arguments.account)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
