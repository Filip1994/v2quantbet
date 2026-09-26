"""QuantLab provider budget backed by the shared football API telemetry."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from h2h.odds.budget import ApiBudgetExceededError


DEFAULT_PROVIDER_DAILY_LIMIT = 75_000


class QuantLabRequestBudget:
    """Share the same restart-safe daily provider envelope as the rest of QuantBet."""

    def __init__(
        self,
        *,
        shared_daily_limit: int = DEFAULT_PROVIDER_DAILY_LIMIT,
        production_reserve: int = 0,
        database_url: str | None = None,
        connect: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            isinstance(shared_daily_limit, bool)
            or not isinstance(shared_daily_limit, int)
            or shared_daily_limit < 1
        ):
            raise ValueError("shared_daily_limit must be a positive integer")
        if (
            isinstance(production_reserve, bool)
            or not isinstance(production_reserve, int)
            or production_reserve < 0
            or production_reserve >= shared_daily_limit
        ):
            raise ValueError("production_reserve must fit inside shared_daily_limit")

        self.daily_limit = shared_daily_limit
        self.shared_daily_limit = shared_daily_limit
        self.production_reserve = production_reserve
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
                (f"quantbet-provider-budget:{day.isoformat()}",),
            )
            cursor.execute(
                "SELECT category, request_count FROM provider_request_usage "
                "WHERE request_day = %s",
                (day,),
            )
            usage = {row[0]: int(row[1]) for row in cursor.fetchall()}
            total = sum(usage.values())

            shared_stop = self.shared_daily_limit - self.production_reserve
            if total >= shared_stop:
                raise ApiBudgetExceededError(
                    f"shared football API budget exhausted: {shared_stop} calls"
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
    def total_used(self) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT category, request_count FROM provider_request_usage "
                "WHERE request_day = %s",
                (self.day,),
            )
            return sum(int(row[1]) for row in cursor.fetchall())

    @property
    def remaining(self) -> int:
        return max(
            0,
            self.shared_daily_limit - self.production_reserve - self.total_used,
        )

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0
