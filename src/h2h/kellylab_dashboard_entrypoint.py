"""Standalone Railway entrypoint for the KellyLab shadow portfolio."""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from threading import Event, Thread

from h2h.api.kellylab_dashboard import KellyLabDashboardService, KellyLabHTTPService
from h2h.logging_config import configure_logging
from h2h.persistence.postgres_kellylab import PostgreSQLKellyLabRepository
from h2h.workers.runtime import install_shutdown_handlers


LOGGER = logging.getLogger(__name__)


def _integer(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _decimal(name: str, default: str) -> Decimal:
    try:
        return Decimal(os.getenv(name, default).strip())
    except Exception as exc:
        raise ValueError(f"{name} must be a decimal") from exc


def _sync_loop(
    stop: Event,
    repository: PostgreSQLKellyLabRepository,
    *,
    interval_seconds: int,
) -> None:
    while not stop.is_set():
        try:
            result = repository.sync_new_picks()
            if result["inserted"]:
                LOGGER.info("KellyLab cloned %s Research pick(s)", result["inserted"])
        except Exception:  # noqa: BLE001 - worker must survive transient DB/read failures
            LOGGER.exception("KellyLab sync failed")
        stop.wait(interval_seconds)


def main() -> None:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    stop = Event()
    install_shutdown_handlers(stop.set)
    repository = PostgreSQLKellyLabRepository(database_url)
    if not repository.check_database():
        raise RuntimeError("KellyLab schema is unavailable")

    repository.ensure_portfolio(
        starting_bankroll_minor=_integer(
            "QUANTBET_KELLYLAB_STARTING_BANKROLL_MINOR",
            "3000000",
        ),
        flat_stake_minor=_integer("QUANTBET_KELLYLAB_FLAT_STAKE_MINOR", "30000"),
        kelly_fraction=_decimal("QUANTBET_KELLYLAB_FRACTION", "0.25"),
        max_bet_fraction=_decimal("QUANTBET_KELLYLAB_MAX_BET_FRACTION", "0.01"),
        calibration_prior_n=_integer("QUANTBET_KELLYLAB_CALIBRATION_PRIOR_N", "100"),
    )
    repository.sync_new_picks()

    dashboard = KellyLabDashboardService(repository)
    server = KellyLabHTTPService(
        dashboard,
        host="0.0.0.0",
        port=_integer("PORT", "8080"),
    )
    sync_thread = Thread(
        target=_sync_loop,
        args=(stop, repository),
        kwargs={
            "interval_seconds": _integer(
                "QUANTBET_KELLYLAB_SYNC_INTERVAL_SECONDS",
                "60",
            )
        },
        daemon=True,
    )
    try:
        server.start()
        sync_thread.start()
        stop.wait()
    finally:
        server.close()
        stop.set()
        sync_thread.join(timeout=5)


if __name__ == "__main__":
    main()
