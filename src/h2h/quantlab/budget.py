"""QuantLab-specific hard request ceiling backed by shared provider telemetry."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from h2h.odds.budget import ApiBudgetExceededError


QUANTLAB_HARD_DAILY_LIMIT = 1000


class QuantLabRequestBudget:
    """Atomically cap QuantLab and preserve provider capacity for production."""

    def __init__(
        self,
        *,
        daily_limit: int = QUANTLAB_HARD_DAILY_LIMIT,
        shared_daily_limit: int = 7500,
        production_reserve: int = 1500,
        database_url: str | None = None,
        connect: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        for name, value in (
            ("daily_limit", daily_limit),
            ("shared_daily_limit", shared_daily_limit),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(production_reserve, bool)
            or not isinstance(production_reserve, int)
            or production_reserve < 0
            or production_reserve >= shared_daily_limit
        ):
            raise ValueError("production_reserve must fit inside shared_daily_limit")

        # Configuration may reduce QuantLab capacity but can never raise the hard ceiling.
        self.daily_limit = min(daily_limit, QUANTLAB_HARD_DAILY_LIMIT)
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
            used = usage.get("quantlab_context", 0)
            total = sum(usage.values())

            if used >= self.daily_limit:
                raise ApiBudgetExceededError(
                    f"QuantLab daily API budget exhausted: {self.daily_limit} calls"
                )
            shared_quantlab_stop = self.shared_daily_limit - self.production_reserve
            if total >= shared_quantlab_stop:
                raise ApiBudgetExceededError(
                    "QuantLab stopped at reserved production provider capacity"
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
