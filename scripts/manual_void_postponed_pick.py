"""Append an audited manual VOID and stake refund for one postponed production pick.

Requires DATABASE_URL or DATABASE_PUBLIC_URL. Inspection is the default; --apply
commits the append-only settlement and ledger entries in one transaction.
"""

from __future__ import annotations

import argparse
import os
from hashlib import sha256

import psycopg


RULE = "MANUAL_POSTPONEMENT_VOID_V1"


def fact_id(prefix: str, value: str) -> str:
    return f"{prefix}:{sha256(value.encode()).hexdigest()}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pick_id")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.actor.strip() or not args.reason.strip():
        parser.error("actor and reason must be nonblank")
    database_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_PUBLIC_URL or DATABASE_URL is required")

    with psycopg.connect(database_url) as connection:  # noqa: SIM117
        with connection.cursor() as cursor:
            # Match the normal settlement lock order: fixture, account, pick.
            cursor.execute(
                "SELECT fixture_id, bankroll_account_id FROM registered_picks WHERE pick_id=%s",
                (args.pick_id,),
            )
            identity = cursor.fetchone()
            if identity is None:
                raise LookupError("pick not found")
            fixture_id, account_id = identity
            cursor.execute("SELECT fixture_id FROM fixtures WHERE fixture_id=%s FOR UPDATE", (fixture_id,))
            if cursor.fetchone() is None:
                raise RuntimeError("fixture missing")
            cursor.execute(
                "SELECT currency FROM bankroll_accounts WHERE bankroll_account_id=%s FOR UPDATE",
                (account_id,),
            )
            account = cursor.fetchone()
            if account is None:
                raise RuntimeError("bankroll account missing")
            cursor.execute(
                "SELECT r.entry_snapshot_id, r.stake_minor, r.currency, "
                "q.odd::text::numeric FROM registered_picks r "
                "JOIN quote_snapshots q ON q.snapshot_id=r.entry_snapshot_id "
                "WHERE r.pick_id=%s FOR UPDATE OF r",
                (args.pick_id,),
            )
            pick = cursor.fetchone()
            if pick is None or pick[2] != account[0]:
                raise RuntimeError("pick/account mismatch")
            snapshot_id, stake_minor, currency, entry_odd = pick
            cursor.execute(
                "SELECT event_kind, outcome FROM pick_settlement_events WHERE pick_id=%s",
                (args.pick_id,),
            )
            existing = cursor.fetchall()
            if existing:
                raise RuntimeError(f"pick already has settlement events: {existing}")
            cursor.execute(
                "SELECT result_observation_id, provider_status, result_classification, "
                "first_acquired_at FROM fixture_result_observations WHERE fixture_id=%s "
                "ORDER BY first_acquired_at DESC, result_observation_id DESC LIMIT 1",
                (fixture_id,),
            )
            result = cursor.fetchone()
            if result is None or result[1:3] != ("PST", "NON_TERMINAL"):
                raise RuntimeError(f"latest provider evidence is not PST: {result}")
            cursor.execute(
                "SELECT ledger_entry_id, amount_minor FROM bankroll_ledger_entries "
                "WHERE pick_id=%s AND entry_type='STAKE_RESERVED'",
                (args.pick_id,),
            )
            reservation = cursor.fetchone()
            if reservation is None or reservation[1] != -stake_minor:
                raise RuntimeError("exact stake reservation missing")
            cursor.execute(
                "SELECT account_sequence, balance_after_minor FROM bankroll_ledger_entries "
                "WHERE bankroll_account_id=%s ORDER BY account_sequence DESC LIMIT 1",
                (account_id,),
            )
            latest = cursor.fetchone()
            if latest is None:
                raise RuntimeError("bankroll ledger missing")
            cursor.execute("SELECT CURRENT_TIMESTAMP")
            now = cursor.fetchone()[0]
            print(
                f"pick={args.pick_id} fixture={fixture_id} provider_status={result[1]} "
                f"stake_refund={stake_minor} {currency} minor units existing_events=0 "
                f"apply={args.apply}"
            )
            if not args.apply:
                connection.rollback()
                return

            ledger_id = fact_id("bankroll-entry-v1", f"manual-postponement-void:{args.pick_id}")
            event_id = fact_id("pick-settlement-event-v1", f"manual-postponement-void:{args.pick_id}")
            cursor.execute(
                "INSERT INTO bankroll_ledger_entries (ledger_entry_id, bankroll_account_id, "
                "account_sequence, entry_type, amount_minor, balance_after_minor, occurred_at, "
                "pick_id) VALUES (%s,%s,%s,'VOID_REFUND',%s,%s,%s,%s)",
                (ledger_id, account_id, latest[0] + 1, stake_minor,
                 latest[1] + stake_minor, now, args.pick_id),
            )
            cursor.execute(
                "INSERT INTO pick_settlement_events (settlement_event_id, pick_id, fixture_id, "
                "event_kind, prior_event_id, result_observation_id, outcome, "
                "settlement_rule_version, rounding_version, entry_snapshot_id, "
                "entry_odd_decimal, stake_minor, gross_return_minor, realized_pnl_minor, "
                "ledger_delta_minor, bankroll_account_id, currency, ledger_entry_id, "
                "candidate_first_seen_at, confirmed_at, confirmation_count, request_id, "
                "reason, actor, occurred_at) VALUES "
                "(%s,%s,%s,'MANUAL_VOID',NULL,%s,'VOID',%s,'MONEY_HALF_UP_V1',"
                "%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s)",
                (event_id, args.pick_id, fixture_id, result[0], RULE, snapshot_id,
                 entry_odd, stake_minor, stake_minor, stake_minor, account_id, currency,
                 ledger_id, result[3], now, f"manual-postponement-void:{args.pick_id}",
                 args.reason, args.actor, now),
            )
            print(f"committed settlement_event={event_id} ledger_entry={ledger_id}")


if __name__ == "__main__":
    main()
