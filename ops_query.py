from __future__ import annotations

import os
from hashlib import sha256

import psycopg

PICK_ID = "registered-pick-v1:399dbe7be91b67243982ae29aed91b2408a857ea27725d6e82c5e31534061f8d"
EXPECTED_FIXTURE = "api-football:1636701"
RULE = "MANUAL_POSTPONEMENT_VOID_V1"
ACTOR = "chatgpt-railway-ops"
REASON = "Manual VOID: Cumbaya - Santo Domingo cancelled; explicit operator instruction."


def fact_id(prefix: str, value: str) -> str:
    return f"{prefix}:{sha256(value.encode()).hexdigest()}"


database_url = os.environ["DATABASE_URL"]
with psycopg.connect(database_url) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT r.fixture_id, r.bankroll_account_id, r.market, r.selection, "
            "f.provider_fixture_id FROM registered_picks r "
            "JOIN fixtures f ON f.fixture_id=r.fixture_id "
            "WHERE r.pick_id=%s",
            (PICK_ID,),
        )
        identity = cursor.fetchone()
        if identity is None:
            raise RuntimeError("target pick not found")
        fixture_id, account_id, market, selection, provider_fixture_id = identity
        if fixture_id != EXPECTED_FIXTURE or str(provider_fixture_id) != "1636701":
            raise RuntimeError(f"target fixture mismatch: {identity}")

        cursor.execute(
            "SELECT home_team, away_team, competition_name FROM fixture_observations "
            "WHERE fixture_id=%s ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
            (fixture_id,),
        )
        fixture = cursor.fetchone()
        if fixture is None:
            raise RuntimeError("fixture observation missing")
        home, away, competition = fixture
        if home != "Cumbayá" or away != "Santo Domingo":
            raise RuntimeError(f"target teams mismatch: {fixture}")

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
            "SELECT r.entry_snapshot_id, r.stake_minor, r.currency, q.odd::text::numeric "
            "FROM registered_picks r JOIN quote_snapshots q ON q.snapshot_id=r.entry_snapshot_id "
            "WHERE r.pick_id=%s FOR UPDATE OF r",
            (PICK_ID,),
        )
        pick = cursor.fetchone()
        if pick is None or pick[2] != account[0]:
            raise RuntimeError("pick/account mismatch")
        snapshot_id, stake_minor, currency, entry_odd = pick

        cursor.execute(
            "SELECT settlement_event_id, event_kind, outcome FROM pick_settlement_events WHERE pick_id=%s",
            (PICK_ID,),
        )
        existing = cursor.fetchall()
        if existing:
            print(f"ALREADY_SETTLED={existing}")
            connection.rollback()
            raise SystemExit(0)

        cursor.execute(
            "SELECT result_observation_id, provider_status, result_classification, first_acquired_at "
            "FROM fixture_result_observations WHERE fixture_id=%s "
            "ORDER BY first_acquired_at DESC, result_observation_id DESC LIMIT 1",
            (fixture_id,),
        )
        result = cursor.fetchone()
        if result is None:
            raise RuntimeError("no result observation exists")
        result_observation_id, provider_status, result_classification, first_acquired_at = result
        if result_classification not in ("NON_TERMINAL", "NON_PLAYED_VOIDABLE"):
            raise RuntimeError(
                f"refusing manual void for classification={result_classification} status={provider_status}"
            )

        cursor.execute(
            "SELECT ledger_entry_id, amount_minor FROM bankroll_ledger_entries "
            "WHERE pick_id=%s AND entry_type='STAKE_RESERVED'",
            (PICK_ID,),
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
        ledger_id = fact_id("bankroll-entry-v1", f"manual-postponement-void:{PICK_ID}")
        event_id = fact_id("pick-settlement-event-v1", f"manual-postponement-void:{PICK_ID}")

        cursor.execute(
            "INSERT INTO bankroll_ledger_entries (ledger_entry_id, bankroll_account_id, "
            "account_sequence, entry_type, amount_minor, balance_after_minor, occurred_at, pick_id) "
            "VALUES (%s,%s,%s,'VOID_REFUND',%s,%s,%s,%s)",
            (
                ledger_id,
                account_id,
                latest[0] + 1,
                stake_minor,
                latest[1] + stake_minor,
                now,
                PICK_ID,
            ),
        )
        cursor.execute(
            "INSERT INTO pick_settlement_events (settlement_event_id, pick_id, fixture_id, "
            "event_kind, prior_event_id, result_observation_id, outcome, settlement_rule_version, "
            "rounding_version, entry_snapshot_id, entry_odd_decimal, stake_minor, "
            "gross_return_minor, realized_pnl_minor, ledger_delta_minor, bankroll_account_id, "
            "currency, ledger_entry_id, candidate_first_seen_at, confirmed_at, "
            "confirmation_count, request_id, reason, actor, occurred_at) VALUES "
            "(%s,%s,%s,'MANUAL_VOID',NULL,%s,'VOID',%s,'MONEY_HALF_UP_V1',"
            "%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s)",
            (
                event_id,
                PICK_ID,
                fixture_id,
                result_observation_id,
                RULE,
                snapshot_id,
                entry_odd,
                stake_minor,
                stake_minor,
                stake_minor,
                account_id,
                currency,
                ledger_id,
                first_acquired_at,
                now,
                f"manual-postponement-void:{PICK_ID}",
                REASON,
                ACTOR,
                now,
            ),
        )

        print(
            "VOID_COMMITTED "
            f"pick_id={PICK_ID} fixture_id={fixture_id} teams={home}-{away} "
            f"provider_status={provider_status} result_classification={result_classification} "
            f"market={market} selection={selection} stake_refund_minor={stake_minor} "
            f"settlement_event={event_id} ledger_entry={ledger_id}"
        )
