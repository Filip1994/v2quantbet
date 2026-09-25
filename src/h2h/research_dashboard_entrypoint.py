"""Standalone Railway entrypoint for the exposure research dashboard."""

from __future__ import annotations

import os
from threading import Event

from h2h.api.research_dashboard import (
    ResearchDashboardHTTPService,
    ResearchDashboardService,
)
from h2h.logging_config import configure_logging
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository
from h2h.workers.runtime import install_shutdown_handlers


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required research dashboard configuration: {name}")
    return value


def _integer(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    stop = Event()
    install_shutdown_handlers(stop.set)
    database_url = _required("DATABASE_URL")
    runtime = PostgreSQLRuntimeRepository(database_url)
    if not runtime.check_database():
        raise RuntimeError("PostgreSQL is unavailable")
    service = ResearchDashboardService(
        database_url,
        fixed_stake_minor=_integer("QUANTBET_FIXED_STAKE_MINOR", "30000"),
    )
    server = ResearchDashboardHTTPService(
        service,
        host="0.0.0.0",
        port=_integer("PORT", "8080"),
    )
    try:
        server.start()
        stop.wait()
    finally:
        server.close()


if __name__ == "__main__":
    main()
