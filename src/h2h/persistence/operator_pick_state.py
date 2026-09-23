"""PostgreSQL persistence for append-only operator pick-state events."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from h2h.domain.operator_pick_state import OperatorPickState, OperatorPickStateEvent


ConnectionFactory = Callable[[], Any]


class OperatorPickStateConflictError(ValueError):
    """An idempotency key contradicts an already persisted operator action."""


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
    ) -> OperatorPickStateEvent:
        if not isinstance(state, OperatorPickState):
            raise TypeError("state must be an OperatorPickState")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        occurred = occurred_at.astimezone(UTC)
        event_id = (
            "pick-operator-state-event-v1:" + sha256(request_id.strip().encode("utf-8")).hexdigest()
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, pick_id, state, occurred_at, request_id "
                "FROM pick_operator_state_events WHERE request_id = %s",
                (request_id.strip(),),
            )
            existing = cursor.fetchone()
            if existing is not None:
                event = self._event(existing)
                if event.pick_id != pick_id or event.state is not state:
                    raise OperatorPickStateConflictError(
                        "request_id already belongs to a different operator action"
                    )
                return event
            cursor.execute("SELECT pick_id FROM registered_picks WHERE pick_id = %s", (pick_id,))
            if cursor.fetchone() is None:
                raise LookupError(f"registered pick {pick_id!r} does not exist")
            cursor.execute(
                "INSERT INTO pick_operator_state_events "
                "(event_id, pick_id, state, occurred_at, request_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (event_id, pick_id, state.value, occurred, request_id.strip()),
            )
        return OperatorPickStateEvent(event_id, pick_id, state, occurred, request_id.strip())

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
