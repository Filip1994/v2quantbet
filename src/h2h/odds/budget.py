"""Daily API-call budget enforcement for provider transports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from threading import Lock
from typing import Any

from .http import JsonTransport


class ApiBudgetExceededError(RuntimeError):
    """Raised before a request when the daily API budget is exhausted."""


@dataclass
class DailyApiBudget:
    """Thread-safe UTC-day budget that counts every attempted request."""

    daily_limit: int = 7500
    reserve: int = 1500
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
