"""Standalone Railway entrypoint for the read-only dashboard."""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Event
from types import SimpleNamespace
from typing import Any

from h2h.api.dashboard import DashboardHTTPService, DashboardService
from h2h.logging_config import configure_logging
from h2h.odds import PostgreSQLApiBudget
from h2h.persistence import PostgreSQLPerformanceRepository
from h2h.persistence.operator_pick_state import PostgreSQLOperatorPickStateRepository
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository
from h2h.workers.runtime import install_shutdown_handlers


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required dashboard configuration: {name}")
    return value


def _integer(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass
class DashboardApplication:
    """Minimal dashboard dependencies; no provider client or worker is composed."""

    settings: Any
    runtime: PostgreSQLRuntimeRepository
    results: Any
    budget: PostgreSQLApiBudget
    operator_picks: PostgreSQLOperatorPickStateRepository


def build_dashboard_application() -> DashboardApplication:
    database_url = _required("DATABASE_URL")
    account_id = _required("QUANTBET_BANKROLL_ACCOUNT_ID")
    initial_minor = _integer("QUANTBET_INITIAL_BANKROLL_MINOR", "3000000")
    daily_limit = _integer("QUANTBET_API_DAILY_LIMIT", "7500")
    reserve = _integer("QUANTBET_API_RESERVE", "0")
    effective_limit = daily_limit - reserve
    training_limit = _integer(
        "QUANTBET_MODEL_TRAINING_DAILY_REQUEST_LIMIT", str(effective_limit)
    )
    operational_reserve = _integer("QUANTBET_MODEL_TRAINING_OPERATIONAL_RESERVE", "0")
    policy = SimpleNamespace(
        bankroll_account_id=account_id,
        initial_bankroll_minor=initial_minor,
    )
    return DashboardApplication(
        settings=SimpleNamespace(
            application=SimpleNamespace(registration_policy=policy)
        ),
        runtime=PostgreSQLRuntimeRepository(database_url),
        results=SimpleNamespace(
            performance=PostgreSQLPerformanceRepository(database_url)
        ),
        budget=PostgreSQLApiBudget(
            daily_limit=daily_limit,
            reserve=reserve,
            training_daily_limit=training_limit,
            operational_reserve=operational_reserve,
            database_url=database_url,
        ),
        operator_picks=PostgreSQLOperatorPickStateRepository(database_url=database_url),
    )


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    stop = Event()
    install_shutdown_handlers(stop.set)
    application = build_dashboard_application()
    if not application.runtime.check_database():
        raise RuntimeError("PostgreSQL is unavailable")
    port = _integer("PORT", "8080")
    server = DashboardHTTPService(
        DashboardService(application), host="0.0.0.0", port=port
    )
    try:
        server.start()
        stop.wait()
    finally:
        server.close()


if __name__ == "__main__":
    main()
