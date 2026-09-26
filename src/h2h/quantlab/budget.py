"""QuantLab-specific hard request ceiling backed by shared provider telemetry."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from h2h.odds.budget import ApiBudgetExceededError


class QuantLabRequestBudget:
    """Atomically cap only the quantlab_context category, independent of production usage."""

    def __init__(
        self,
        *,
        daily_limit: int = 1000,
        database_url: str | None = None,
        connect: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if isinstance(daily_limit, bool) or not isinstance(daily_limit, int) or daily_limit < 1:
            raise ValueError("daily_limit must be a positive integer")
        self.daily_limit = daily_limit
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect
        self.clock = clock

    def _connect(self) -> Any:
        if self._connect_factory is not None:
            return self._connect_factory()
        import psycopg

        return psycopg.connect(self._database_url)

    @property
    def day(self):
        return self.clock().astimezone(UTC).date()

    def acquire(self) -> None:
        day = self.day
        now = self.clock().astimezone(UTC)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"quantlab-context-budget:{day.isoformat()}",),
            )
            cursor.execute(
                "SELECT COALESCE(request_count, 0) FROM provider_request_usage "
                "WHERE request_day = %s AND category = 'quantlab_context'",
                (day,),
            )
            row = cursor.fetchone()
            used = 0 if row is None else int(row[0])
            if used >= self.daily_limit:
                raise ApiBudgetExceededError(
                    f"QuantLab daily API budget exhausted: {self.daily_limit} calls"
                )
            cursor.execute(
                "INSERT INTO provider_request_usage "
                "(request_day, category, request_count, updated_at) "
                "VALUES (%s, 'quantlab_context', 1, %s) "
                "ON CONFLICT (request_day, category) DO UPDATE SET "
                "request_count = provider_request_usage.request_count + 1, "
                "updated_at = EXCLUDED.updated_at",
                (day, now),
            )

    @property
    def used(self) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(request_count, 0) FROM provider_request_usage "
                "WHERE request_day = %s AND category = 'quantlab_context'",
                (self.day,),
            )
            row = cursor.fetchone()
            return 0 if row is None else int(row[0])

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0
