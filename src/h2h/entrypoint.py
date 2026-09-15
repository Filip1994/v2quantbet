"""Production entrypoint for the QuantBet history worker."""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from time import monotonic
from threading import Event

from h2h.application import build_api_football_client
from h2h.application import build_postgres_quote_history_application_from_settings
from h2h.config import load_settings
from h2h.domain.fixture_identity import (
    ResolvedFixtureIdentity,
    api_football_fixture_identity,
)
from h2h.odds import ApiFootballOddsService
from h2h.odds.http import UrllibJsonTransport
from h2h.use_cases.api_football_fixture_discovery import ApiFootballFixtureDiscovery
from h2h.use_cases.scoped_fixture_discovery import ScopedFixtureDiscovery
from h2h.workers.discovered_history_quote_polling import DiscoveredHistoryQuotePollingJob
from h2h.workers.history_quote_polling import HistoryQuotePollingJob
from h2h.workers.runtime import WorkerRuntime, install_shutdown_handlers

LOGGER = logging.getLogger("quantbet.worker")


def _fixture_identities_from_environment() -> tuple[ResolvedFixtureIdentity, ...]:
    """Read the optional API-Football allowlist as resolved fixture identities."""
    raw = os.getenv("QUANTBET_FIXTURE_IDS", "").strip()
    if not raw:
        return ()
    try:
        fixture_ids = tuple(int(value.strip()) for value in raw.split(","))
    except ValueError as exc:
        raise ValueError("QUANTBET_FIXTURE_IDS must contain integers") from exc
    if not fixture_ids or any(fixture_id <= 0 for fixture_id in fixture_ids):
        raise ValueError("QUANTBET_FIXTURE_IDS must contain positive integers")
    return tuple(api_football_fixture_identity(fixture_id) for fixture_id in fixture_ids)


def _positive_seconds(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def main() -> None:
    """Initialize PostgreSQL and run the configured pre-match polling worker."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = load_settings()
    manual_fixture_identities = _fixture_identities_from_environment()
    application = build_postgres_quote_history_application_from_settings(settings)
    applied = application.migrate()
    LOGGER.info("PostgreSQL ready; migrations applied: %s", applied)

    client = build_api_football_client(UrllibJsonTransport(), settings)
    source = ApiFootballOddsService(client)
    stopped = Event()
    install_shutdown_handlers(stopped.set)

    poll_interval = _positive_seconds("QUANTBET_POLL_INTERVAL_SECONDS", 60.0)
    discovery_interval = _positive_seconds("QUANTBET_DISCOVERY_INTERVAL_SECONDS", 900.0)
    lookahead_hours = _positive_seconds("QUANTBET_DISCOVERY_LOOKAHEAD_HOURS", 72.0)

    if manual_fixture_identities:
        poll_job = HistoryQuotePollingJob(
            source,
            application.service,
            manual_fixture_identities,
        )
        LOGGER.warning(
            "QUANTBET_FIXTURE_IDS is configured; using manual fixture allowlist instead of discovery"
        )
        discovery_refresh = None
    else:
        discovery = ScopedFixtureDiscovery(ApiFootballFixtureDiscovery(client))
        discovered_job = DiscoveredHistoryQuotePollingJob(
            source,
            application.service,
            discovery,
            lookahead=timedelta(hours=lookahead_hours),
        )
        poll_job = None
        last_discovery_at: float | None = None
        LOGGER.info(
            "Starting discovery-driven worker: poll=%ss discovery=%ss lookahead=%sh",
            poll_interval,
            discovery_interval,
            lookahead_hours,
        )

        def discovery_refresh() -> None:
            nonlocal last_discovery_at
            now = monotonic()
            if last_discovery_at is None or now - last_discovery_at >= discovery_interval:
                total = discovered_job.run_once()
                last_discovery_at = now
                LOGGER.info("Discovery cycle persisted %s snapshots", total)
            else:
                LOGGER.debug(
                    "Skipping discovery cycle; next refresh due in %.1fs",
                    discovery_interval - (now - last_discovery_at),
                )

    def run_cycle() -> None:
        if poll_job is not None:
            total = poll_job.run_once()
            LOGGER.info("Worker cycle persisted %s snapshots", total)
            return
        discovery_refresh()

    WorkerRuntime(
        job=run_cycle,
        interval_seconds=poll_interval,
        should_stop=stopped.is_set,
    ).run_forever()
    LOGGER.info("QuantBet worker stopped")


if __name__ == "__main__":
    main()
