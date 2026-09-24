"""Shared PostgreSQL helpers for operator-effective open risk exposure."""

from __future__ import annotations

from typing import Any


_EFFECTIVE_PLAYED_OPEN_EXPOSURE_SQL = (
    "WITH latest_operator AS ("
    "SELECT DISTINCT ON (pick_id) pick_id, state "
    "FROM pick_operator_state_events "
    "ORDER BY pick_id, occurred_at DESC, persisted_at DESC, event_id DESC"
    ") "
    "SELECT COALESCE(SUM(-l.amount_minor), 0) "
    "FROM bankroll_ledger_entries l "
    "LEFT JOIN latest_operator o ON o.pick_id = l.pick_id "
    "WHERE l.bankroll_account_id = %s AND l.entry_type = 'STAKE_RESERVED' "
    "AND COALESCE(o.state, 'PLAYED') = 'PLAYED' "
    "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events e "
    "WHERE e.pick_id = l.pick_id AND e.outcome IS NOT NULL "
    "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events successor "
    "WHERE successor.prior_event_id = e.settlement_event_id))"
)

_UNRESOLVED_RESERVATION_SQL = (
    "SELECT EXISTS (SELECT 1 FROM bankroll_ledger_entries l "
    "WHERE l.pick_id = %s AND l.entry_type = 'STAKE_RESERVED' "
    "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events e "
    "WHERE e.pick_id = l.pick_id AND e.outcome IS NOT NULL "
    "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events successor "
    "WHERE successor.prior_event_id = e.settlement_event_id)))"
)


def effective_played_open_exposure(cursor: Any, bankroll_account_id: str) -> int:
    """Return unresolved reserved exposure for effective PLAYED picks."""
    cursor.execute(_EFFECTIVE_PLAYED_OPEN_EXPOSURE_SQL, (bankroll_account_id,))
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("effective open exposure query returned no row")
    return int(row[0])


def has_unresolved_reservation(cursor: Any, pick_id: str) -> bool:
    """Return whether a pick still owns an unresolved stake reservation."""
    cursor.execute(_UNRESOLVED_RESERVATION_SQL, (pick_id,))
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("reservation state query returned no row")
    return bool(row[0])
