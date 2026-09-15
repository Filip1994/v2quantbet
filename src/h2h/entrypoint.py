"""Production entrypoint for the QuantBet history worker."""

from __future__ import annotations

import logging
import os
from threading import Event

from h2h.application import build_api_football_client
from h2h.application import build_postgres_quote_history_application_from_settings
from h2h.config import load_settings
from h2h.odds import ApiFootballOddsService
from h2h.odds.http import UrllibJsonTransport
from h2h.workers.history_quote_polling import HistoryQuotePollingJob
from h2h.workers.runtime import WorkerRuntime, install_shutdown_handlers

LOGGER = logging.getLogger("quantbet.worker")


def _fixture_ids_from_environment() -> tuple[int, ...]:
    """Read the optional comma-separated fixture allowlist."""
    raw = os.getenv("QUANTBET_FIXTURE_IDS", "").strip()
    if not raw:
        return ()
    try:
        fixture_ids = tuple(int(value.strip()) for value in raw.split(","))
    except ValueError as exc:
        raise ValueError("QUANTBET_FIXTURE_IDS must contain integers") from exc
    if not fixture_ids or any(fixture_id <= 0 for fixture_id in fixture_ids):
        raise ValueError("QUANTBET_FIXTURE_IDS must contain positive integers")
    return fixture_ids


def main() -> None:
    """Initialize PostgreSQL and run the configured pre-match polling worker."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = load_settings()
    fixture_ids = _fixture_ids_from_environment()
    application = build_postgres_quote_history_application_from_settings(settings)
    applied = application.migrate()
    LOGGER.info("PostgreSQL ready; migrations applied: %s", applied)

    stopped = Event()
    install_shutdown_handlers(stopped.set)

    if not fixture_ids:
        LOGGER.warning(
            "QUANTBET_FIXTURE_IDS is not configured; worker is idle until fixture discovery is wired"
        )

        def idle_job() -> None:
            LOGGER.info("Worker idle: no fixture IDs configured")

        job_callback = idle_job
    else:
        client = build_api_football_client(UrllibJsonTransport(), settings)
        source = ApiFootballOddsService(client)
        job = HistoryQuotePollingJob(source, application.service, fixture_ids)
        LOGGER.info("Starting QuantBet worker for fixtures: %s", fixture_ids)
        job_callback = job.run_once

    WorkerRuntime(
        job=job_callback,
        interval_seconds=float(os.getenv("QUANTBET_POLL_INTERVAL_SECONDS", "60")),
        should_stop=stopped.is_set,
    ).run_forever()
    LOGGER.info("QuantBet worker stopped")


if __name__ == "__main__":
    main()
