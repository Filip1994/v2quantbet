from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from h2h.odds.budget import (
    ApiBudgetExceededError,
    BudgetedJsonTransport,
    DailyApiBudget,
)


def test_budget_keeps_operational_reserve() -> None:
    budget = DailyApiBudget(daily_limit=5, reserve=2)

    for _ in range(3):
        budget.acquire()

    assert budget.used == 3
    assert budget.remaining == 0
    with pytest.raises(ApiBudgetExceededError):
        budget.acquire()


def test_budget_resets_on_next_utc_day() -> None:
    now = [datetime(2026, 9, 14, tzinfo=UTC)]
    budget = DailyApiBudget(daily_limit=2, reserve=0, clock=lambda: now[0])
    budget.acquire()
    now[0] = datetime(2026, 9, 15, tzinfo=UTC)

    budget.acquire()

    assert budget.used == 1


def test_budgeted_transport_does_not_call_underlying_transport_after_limit() -> None:
    transport = Mock()
    transport.get_json.return_value = {"response": []}
    budget = DailyApiBudget(daily_limit=1, reserve=0)
    guarded = BudgetedJsonTransport(transport, budget)

    guarded.get_json("https://example.test")
    with pytest.raises(ApiBudgetExceededError):
        guarded.get_json("https://example.test")

    assert transport.get_json.call_count == 1


def test_budget_counts_failed_attempts() -> None:
    transport = Mock()
    transport.get_json.side_effect = RuntimeError("failure")
    guarded = BudgetedJsonTransport(
        transport,
        DailyApiBudget(daily_limit=1, reserve=0),
    )

    with pytest.raises(RuntimeError):
        guarded.get_json("https://example.test")
    with pytest.raises(ApiBudgetExceededError):
        guarded.get_json("https://example.test")
