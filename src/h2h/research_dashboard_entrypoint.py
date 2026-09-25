"""Standalone Railway entrypoint for the exposure research dashboard."""

from __future__ import annotations

import os
from threading import Event

from h2h.api.research_dashboard import (
    ResearchDashboardHTTPService,
    build_research_dashboard_from_environment,
)
from h2h.logging_config import configure_logging
from h2h.workers.runtime import install_shutdown_handlers


def _integer(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    stop = Event()
    install_shutdown_handlers(stop.set)
    dashboard = build_research_dashboard_from_environment()
    port = _integer("PORT", "8080")
    server = ResearchDashboardHTTPService(dashboard, host="0.0.0.0", port=port)
    try:
        server.start()
        stop.wait()
    finally:
        server.close()


if __name__ == "__main__":
    main()
