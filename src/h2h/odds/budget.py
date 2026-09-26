"""Daily API-call budget enforcement for provider transports."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from threading import Lock
from typing import Any

from .http import JsonTransport


class ApiBudgetExceededError(RuntimeError):
    """Raised before a request when the daily API budget is exhausted."""


PROVIDER_REQUEST_CATEGORIES = (
    "discovery",
    "model_training",
    "opportunity_odds",
    "results_monitoring",
    "quantlab_context",
)
_REQUEST_CATEGORY: ContextVar[str] = ContextVar(
    "provider_request_category", default="opportunity_odds"
)


@contextmanager
def provider_request_category(category: str) -> Iterator[None]:
    if category not in PROVIDER_REQUEST_CATEGORIES:
        raise ValueError(f"unsupported provider request category: {category!r}")
    token = _REQUEST_CATEGORY.set(category)
    try:
        yield
    finally:
        _REQUEST_CATEGORY.reset(token)


@dataclass
class DailyApiBudget:
    """Thread-safe UTC-day budget that counts every attempted request."""

    daily_limit: int = 7500
    reserve: int = 0
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _day: date = field(init=False)
    _used: int = field(default=0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.daily_limit < 1:
            raise ValueError("daily_limit must be at least one")
        if self.reserve < 0 or self.reserve >= self.daily_limit:
            raise ValueError("reserve must be non-negative and below daily_limit")
        self._day = self.clock().date()

    @property
    def effective_limit(self) -> int:
        """Maximum calls allowed by the operational budget."""
        return self.daily_limit - self.reserve

    @property
    def day(self) -> date:
        with self._lock:
            self._reset_if_needed()
            return self._day

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    @property
    def used(self) -> int:
        with self._lock:
            self._reset_if_needed()
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            self._reset_if_needed()
            return self.effective_limit - self._used

    def acquire(self) -> None:
        """Reserve one API call, or raise without making a network request."""
        with self._lock:
            self._reset_if_needed()
            if self._used >= self.effective_limit:
                raise ApiBudgetExceededError(
                    f"daily API budget exhausted: {self.effective_limit} calls"
                )
            self._used += 1

    def _reset_if_needed(self) -> None:
        current_day = self.clock().date()
        if current_day != self._day:
            self._day = current_day
            self._used = 0


class PostgreSQLApiBudget:
    """Restart-safe categorized provider budget shared by all service clients."""

    def __init__(
        self,
        *,
        daily_limit: int,
        reserve: int,
        training_daily_limit: int,
        operational_reserve: int,
        database_url: str | None = None,
        connect: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if daily_limit < 1:
            raise ValueError("daily_limit must be at least one")
        if reserve < 0 or reserve >= daily_limit:
            raise ValueError("reserve must be non-negative and below daily_limit")
        effective = daily_limit - reserve
        if training_daily_limit < 1 or training_daily_limit > effective:
            raise ValueError("training_daily_limit must fit inside the effective limit")
        if operational_reserve < 0 or operational_reserve >= effective:
            raise ValueError("operational_reserve must be below the effective limit")
        self.daily_limit = daily_limit
        self.reserve = reserve
        self.training_daily_limit = training_daily_limit
        self.operational_reserve = operational_reserve
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect
        self.clock = clock

    @property
    def effective_limit(self) -> int:
        return self.daily_limit - self.reserve

    @property
    def day(self) -> date:
        return self.clock().astimezone(UTC).date()

    def _connect(self) -> Any:
        if self._connect_factory is not None:
            return self._connect_factory()
        import psycopg

        return psycopg.connect(self._database_url)

    def acquire(self) -> None:
        category = _REQUEST_CATEGORY.get()
        if category not in PROVIDER_REQUEST_CATEGORIES:
            raise ApiBudgetExceededError("provider request category is not authorized")
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
            if total >= self.effective_limit:
                raise ApiBudgetExceededError(
                    f"daily API budget exhausted: {self.effective_limit} calls"
                )
            if category == "model_training":
                if usage.get(category, 0) >= self.training_daily_limit:
                    raise ApiBudgetExceededError("model-training daily allowance exhausted")
                if total >= self.effective_limit - self.operational_reserve:
                    raise ApiBudgetExceededError(
                        "model-training stopped at reserved operational capacity"
                    )
            cursor.execute(
                "INSERT INTO provider_request_usage "
                "(request_day, category, request_count, updated_at) VALUES (%s, %s, 1, %s) "
                "ON CONFLICT (request_day, category) DO UPDATE SET request_count = "
                "provider_request_usage.request_count + 1, updated_at = EXCLUDED.updated_at",
                (day, category, now),
            )

    def usage_by_category(self) -> dict[str, int]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT category, request_count FROM provider_request_usage "
                "WHERE request_day = %s",
                (self.day,),
            )
            stored = {row[0]: int(row[1]) for row in cursor.fetchall()}
        return {category: stored.get(category, 0) for category in PROVIDER_REQUEST_CATEGORIES}

    @property
    def used(self) -> int:
        return sum(self.usage_by_category().values())

    @property
    def remaining(self) -> int:
        return max(0, self.effective_limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0


@dataclass(frozen=True)
class BudgetedJsonTransport:
    """JsonTransport wrapper that enforces a shared daily API budget."""

    transport: JsonTransport
    budget: DailyApiBudget

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Mapping[str, Any]:
        self.budget.acquire()
        return self.transport.get_json(url, headers=headers, timeout=timeout)
