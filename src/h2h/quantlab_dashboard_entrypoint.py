"""Standalone Railway entrypoint for the read-only QuantLab dashboard."""

from __future__ import annotations

import os
from threading import Event

from h2h.logging_config import configure_logging
from h2h.quantlab.dashboard import QuantLabDashboardHTTPService, QuantLabDashboardService
from h2h.quantlab.repository import PostgreSQLQuantLabRepository
from h2h.workers.runtime import install_shutdown_handlers


def _database_url() -> str:
    value = (
        os.getenv("QUANTBET_QUANTLAB_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not value:
        raise ValueError("Missing QUANTBET_QUANTLAB_DATABASE_URL or DATABASE_URL")
    return value


def _positive_integer(name: str, default: str) -> int:
    try:
        value = int(os.getenv(name, default).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def main() -> None:
    """Serve QuantLab UI only; do not compose collector, provider, or modeler work."""
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    stop = Event()
    install_shutdown_handlers(stop.set)

    repository = PostgreSQLQuantLabRepository(_database_url())
    if not repository.check_database():
        raise RuntimeError("QuantLab schema is unavailable")

    dashboard = QuantLabDashboardService(
        repository,
        api_daily_limit=_positive_integer("QUANTBET_API_DAILY_LIMIT", "75000"),
        currency=os.getenv("QUANTBET_CURRENCY", "RSD").strip().upper() or "RSD",
        view_cache_ttl_seconds=_positive_integer(
            "QUANTBET_QUANTLAB_DASHBOARD_CACHE_TTL_SECONDS",
            "60",
        ),
    )
    server = QuantLabDashboardHTTPService(
        dashboard,
        host="0.0.0.0",
        port=_positive_integer("PORT", "8080"),
    )
    try:
        server.start()
        stop.wait()
    finally:
        server.close()


if __name__ == "__main__":
    main()
