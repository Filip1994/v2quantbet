"""Standalone Railway entrypoint for the read-only research dashboard."""

from __future__ import annotations

import os
from threading import Event

from h2h.api.research_dashboard import ResearchDashboardHTTPService, ResearchDashboardService
from h2h.logging_config import configure_logging
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository
from h2h.workers.runtime import install_shutdown_handlers


def _database_url() -> str:
    value = (
        os.getenv("QUANTBET_RESEARCH_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not value:
        raise ValueError("Missing QUANTBET_RESEARCH_DATABASE_URL or DATABASE_URL")
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
    repository = PostgreSQLResearchSignalRepository(_database_url())
    if not repository.check_database():
        raise RuntimeError("research_signals schema is unavailable")
    dashboard = ResearchDashboardService(
        repository,
        fixed_stake_minor=_integer("QUANTBET_FIXED_STAKE_MINOR", "30000"),
        strict_quote_age_seconds=_integer("QUANTBET_MAXIMUM_QUOTE_AGE_SECONDS", "300"),
        provider_snapshot_max_age_seconds=_integer(
            "QUANTBET_API_FOOTBALL_PUBLISHED_MAX_AGE_SECONDS", "28800"
        ),
    )
    server = ResearchDashboardHTTPService(
        dashboard, host="0.0.0.0", port=_integer("PORT", "8080")
    )
    try:
        server.start()
        stop.wait()
    finally:
        server.close()


if __name__ == "__main__":
    main()
