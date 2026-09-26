"""Standalone Railway entrypoint for the read-only QuantLab dashboard."""

from __future__ import annotations

import os
from threading import Event

from h2h.api.quantlab_dashboard import QuantLabDashboardHTTPService, QuantLabDashboardService
from h2h.logging_config import configure_logging
from h2h.persistence.postgres_quantlab import PostgreSQLQuantLabRepository
from h2h.workers.runtime import install_shutdown_handlers


def _database_url() -> str:
    value = (
        os.getenv("QUANTBET_QUANTLAB_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not value:
        raise ValueError("Missing QUANTBET_QUANTLAB_DATABASE_URL or DATABASE_URL")
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
    repository = PostgreSQLQuantLabRepository(_database_url())
    if not repository.check_database():
        raise RuntimeError("quantlab_shadow_bets schema is unavailable")
    dashboard = QuantLabDashboardService(
        repository,
        api_daily_limit=_integer("QUANTBET_QUANTLAB_API_DAILY_LIMIT", "1000"),
        currency=os.getenv("QUANTBET_CURRENCY", "RSD").strip().upper() or "RSD",
    )
    server = QuantLabDashboardHTTPService(
        dashboard, host="0.0.0.0", port=_integer("PORT", "8080")
    )
    try:
        server.start()
        stop.wait()
    finally:
        server.close()


if __name__ == "__main__":
    main()
