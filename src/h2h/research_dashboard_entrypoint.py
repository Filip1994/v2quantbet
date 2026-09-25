"""Standalone Railway entrypoint for the read-only QuantBet research dashboard."""

from __future__ import annotations

import os
from threading import Event

from h2h.api.research_dashboard import (
    ResearchDashboardHTTPService,
    ResearchDashboardService,
)
from h2h.logging_config import configure_logging
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository
from h2h.workers.runtime import install_shutdown_handlers


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required research dashboard configuration: {name}")
    return value


def _positive_integer(name: str) -> int:
    value = _required(name)
    try:
        result = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    stop = Event()
    install_shutdown_handlers(stop.set)

    repository = PostgreSQLResearchSignalRepository(database_url=_required("DATABASE_URL"))
    with repository.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise RuntimeError("PostgreSQL health probe failed")

    server = ResearchDashboardHTTPService(
        ResearchDashboardService(
            repository,
            closing_max_age_seconds=_positive_integer(
                "QUANTBET_CLOSING_MAX_AGE_SECONDS"
            ),
        ),
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080").strip()),
    )
    try:
        server.start()
        stop.wait()
    finally:
        server.close()


if __name__ == "__main__":
    main()
