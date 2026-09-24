"""PostgreSQL persistence for append-only operator pick-state events."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from h2h.domain.operator_pick_state import OperatorPickState, OperatorPickStateEvent
from h2h.persistence.postgres_operator_risk import (
    effective_played_open_exposure,
    has_unresolved_reservation,
)


ConnectionFactory = Callable[[], Any]


class OperatorPickStateConflictError(ValueError):
    """An idempotency key contradicts an already persisted operator action."""


class OperatorPickStateRiskError(ValueError):
    """A PLAYED reactivation would violate the configured hard open-exposure cap."""


class PostgreSQLOperatorPickStateRepository:
    def __init__(
        self, database_url: str | None = None, *, connect: ConnectionFactory | None = None
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect

    def connect(self):
        if self._connect_factory is not None:
            return self._connect_factory()
        import psycopg

        return psycopg.connect(self._database_url)

    def set_state(
        self,
        pick_id: str,
        state: OperatorPickState,
        request_id: str,
        *,
        occurred_at: datetime,
        max_open_exposure_minor: int | None = None,
    ) -> OperatorPickStateEvent:
        if not isinstance(state, OperatorPickState):
            raise TypeError("state must be an OperatorPickState")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        occurred = occurred_at.astimezone(UTC)
        request = request_id.strip()
        event_id = "pick-operator-state-event-v1:" + sha256(request.encode("utf-8")).hexdigest()

        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, pick_id, state, occurred_at, request_id "
                "FROM pick_operator_state_events WHERE request_id = %s",
                (request,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                event = self._event(existing)
                if event.pick_id != pick_id or event.state is not state:
                    raise OperatorPickStateConflictError(
                        "request_id already belongs to a different operator action"
                    )
                return event

            cursor.execute(
                "SELECT bankroll_account_id, stake_minor FROM registered_picks "
                "WHERE pick_id = %s",
                (pick_id,),
            )
            initial = cursor.fetchone()
            if initial is None:
                raise LookupError(f"registered pick {pick_id!r} does not exist")
            account_id, stake_minor = initial

            # Serialize every operator state transition that can change effective exposure
            # with registration and settlement, which already lock this bankroll row.
            cursor.execute(
                "SELECT bankroll_account_id FROM bankroll_accounts "
                "WHERE bankroll_account_id = %s FOR UPDATE",
                (account_id,),
            )
            if cursor.fetchone() is None:
                raise LookupError(f"bankroll account {account_id!r} does not exist")
            cursor.execute(
                "SELECT bankroll_account_id, stake_minor FROM registered_picks "
                "WHERE pick_id = %s FOR UPDATE",
                (pick_id,),
            )
            locked = cursor.fetchone()
            if locked is None or locked != initial:
                raise OperatorPickStateConflictError(
                    "registered pick context changed while locking"
                )

            # A concurrent replay may have committed while this transaction waited.
            cursor.execute(
                "SELECT event_id, pick_id, state, occurred_at, request_id "
                "FROM pick_operator_state_events WHERE request_id = %s",
                (request,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                event = self._event(existing)
                if event.pick_id != pick_id or event.state is not state:
                    raise OperatorPickStateConflictError(
                        "request_id already belongs to a different operator action"
                    )
                return event

            cursor.execute(
                "SELECT state, occurred_at FROM pick_operator_state_events "
                "WHERE pick_id = %s "
                "ORDER BY occurred_at DESC, persisted_at DESC, event_id DESC LIMIT 1",
                (pick_id,),
            )
            latest = cursor.fetchone()
            effective_before = (
                OperatorPickState.PLAYED if latest is None else OperatorPickState(latest[0])
            )
            becomes_latest = latest is None or occurred >= latest[1]
            effective_after = state if becomes_latest else effective_before

            if (
                effective_before != effective_after
                and effective_after is OperatorPickState.PLAYED
                and has_unresolved_reservation(cursor, pick_id)
            ):
                if (
                    isinstance(max_open_exposure_minor, bool)
                    or not isinstance(max_open_exposure_minor, int)
                    or max_open_exposure_minor <= 0
                ):
                    raise OperatorPickStateRiskError(
                        "positive max_open_exposure_minor is required to reactivate "
                        "an unsettled skipped pick"
                    )
                open_exposure = effective_played_open_exposure(cursor, account_id)
                if open_exposure + int(stake_minor) > max_open_exposure_minor:
                    raise OperatorPickStateRiskError(
                        "PLAYED reactivation would exceed maximum open exposure "
                        f"({open_exposure} + {int(stake_minor)} > "
                        f"{max_open_exposure_minor})"
                    )

            cursor.execute(
                "INSERT INTO pick_operator_state_events "
                "(event_id, pick_id, state, occurred_at, request_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (event_id, pick_id, state.value, occurred, request),
            )
        return OperatorPickStateEvent(event_id, pick_id, state, occurred, request)

    def current_state(self, pick_id: str) -> OperatorPickState:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pick_id FROM registered_picks WHERE pick_id = %s", (pick_id,))
            if cursor.fetchone() is None:
                raise LookupError(f"registered pick {pick_id!r} does not exist")
            cursor.execute(
                "SELECT state FROM pick_operator_state_events WHERE pick_id = %s "
                "ORDER BY occurred_at DESC, persisted_at DESC, event_id DESC LIMIT 1",
                (pick_id,),
            )
            row = cursor.fetchone()
        return OperatorPickState.PLAYED if row is None else OperatorPickState(row[0])

    def history(self, pick_id: str) -> tuple[OperatorPickStateEvent, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pick_id FROM registered_picks WHERE pick_id = %s", (pick_id,))
            if cursor.fetchone() is None:
                raise LookupError(f"registered pick {pick_id!r} does not exist")
            cursor.execute(
                "SELECT event_id, pick_id, state, occurred_at, request_id "
                "FROM pick_operator_state_events WHERE pick_id = %s "
                "ORDER BY occurred_at, persisted_at, event_id",
                (pick_id,),
            )
            return tuple(self._event(row) for row in cursor.fetchall())

    def resolve_short_pick_id(self, short_id: str) -> str:
        if (
            not isinstance(short_id, str)
            or len(short_id) != 10
            or any(character not in "0123456789abcdef" for character in short_id.casefold())
        ):
            raise ValueError("short pick id must be exactly 10 hexadecimal characters")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id FROM registered_picks WHERE RIGHT(pick_id, 10) = %s "
                "ORDER BY pick_id LIMIT 2",
                (short_id.casefold(),),
            )
            matches = tuple(row[0] for row in cursor.fetchall())
        if len(matches) != 1:
            raise LookupError(
                f"short pick id {short_id!r} resolved to {len(matches)} registered picks"
            )
        return matches[0]

    @staticmethod
    def _event(row: tuple[Any, ...]) -> OperatorPickStateEvent:
        return OperatorPickStateEvent(row[0], row[1], OperatorPickState(row[2]), row[3], row[4])
