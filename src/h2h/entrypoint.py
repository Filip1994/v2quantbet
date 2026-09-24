"""Production entrypoint for the single-leader QuantBet Railway service."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import uuid4

from h2h.api.health import HealthService, RuntimeHealthState
from h2h.config import load_production_settings
from h2h.domain.fixture_identity import ResolvedFixtureIdentity, api_football_fixture_identity
from h2h.logging_config import configure_logging
from h2h.odds import ApiBudgetExceededError
from h2h.odds.http import TransportError
from h2h.production import ProductionApplication, build_production_application
from h2h.workers.orchestrator import ProductionOrchestrator, ScheduledJob
from h2h.workers.daily_bulletin import DailyBulletinWorker
from h2h.workers.runtime import install_shutdown_handlers


LOGGER = logging.getLogger("quantbet.worker")
MIGRATION_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _expected_migrations() -> tuple[str, ...]:
    return tuple(path.name for path in sorted(MIGRATION_DIR.glob("*.sql")))


def _fixture_identities_from_environment() -> tuple[ResolvedFixtureIdentity, ...]:
    """Legacy parser retained for compatibility; production uses date-window discovery."""
    raw = os.getenv("QUANTBET_FIXTURE_IDS", "").strip()
    if not raw:
        return ()
    try:
        fixture_ids = tuple(int(value.strip()) for value in raw.split(","))
    except ValueError as exc:
        raise ValueError("QUANTBET_FIXTURE_IDS must contain integers") from exc
    if any(fixture_id <= 0 for fixture_id in fixture_ids):
        raise ValueError("QUANTBET_FIXTURE_IDS must contain positive integers")
    return tuple(api_football_fixture_identity(fixture_id) for fixture_id in fixture_ids)


def _connect_with_retry(application: ProductionApplication, stop: Event) -> None:
    settings = application.settings
    last_error: BaseException | None = None
    for attempt in range(settings.database_startup_attempts):
        if stop.is_set():
            raise RuntimeError("shutdown requested during database startup")
        try:
            if application.runtime.check_database():
                return
        except Exception as exc:  # noqa: BLE001 - bounded startup connectivity retry
            last_error = exc
        if attempt + 1 < settings.database_startup_attempts:
            stop.wait(settings.database_startup_backoff_seconds)
    raise RuntimeError("PostgreSQL did not become ready within the startup window") from last_error


def _prepare_bankroll(application: ProductionApplication) -> None:
    policy = application.settings.application.registration_policy
    assert policy is not None
    if application.settings.bankroll_bootstrap_mode == "create":
        application.registration.bootstrap_bankroll.execute()
    application.runtime.verify_bankroll(
        policy.bankroll_account_id, policy.currency, policy.initial_bankroll_minor
    )


def _run_active_leader(
    application: ProductionApplication,
    state: RuntimeHealthState,
    stop: Event,
    leader: object,
    instance_id: str,
) -> bool:
    _prepare_bankroll(application)
    state.update(leadership="active")
    application.monitoring.reconcile.execute()
    application.results.repository.reconcile(reconciled_at=datetime.now(UTC))
    policy = application.settings.application.registration_policy
    lifecycle = application.settings.application.odds_lifecycle_policy
    assert policy is not None and lifecycle is not None
    application.runtime.due_opportunity_fixtures(
        bookmaker_id=application.settings.bookmaker_id,
        allowed_statuses=policy.allowed_fixture_statuses,
        now=datetime.now(UTC),
        maximum_quote_age_seconds=policy.maximum_quote_age_seconds,
        minimum_time_to_kickoff_seconds=policy.minimum_time_to_kickoff_seconds,
        stale_retry_policy=application.settings.stale_quote_retry_policy,
    )

    durable = application.prediction.durable_discovery
    if durable is None:
        raise RuntimeError("durable fixture discovery is not composed")

    bulletin_worker = DailyBulletinWorker(
        application.monitoring.bulletin,
        horizon=timedelta(hours=application.settings.discovery_lookahead_hours),
        timezone=application.settings.application.bulletin_timezone,
    )

    def discovery_cycle() -> int:
        if stop.is_set():
            return 0
        start = datetime.now(UTC)
        fixtures_persisted = len(
            durable.discover(
                start,
                start + timedelta(hours=application.settings.discovery_lookahead_hours),
            )
        )
        LOGGER.info(
            "discovery cycle outcomes",
            extra={"worker": "discovery", "fixtures_persisted": fixtures_persisted},
        )
        return fixtures_persisted

    jobs = (
        ScheduledJob(
            "discovery",
            application.settings.discovery_interval_seconds,
            discovery_cycle,
            has_pending_work=lambda: durable.has_pending,
        ),
        ScheduledJob(
            "model_lifecycle",
            application.settings.model_training_interval_seconds,
            application.model_lifecycle.run_once,
        ),
        ScheduledJob(
            "opportunity",
            application.settings.opportunity_interval_seconds,
            application.opportunity.run_once,
            has_pending_work=lambda: application.opportunity.has_pending,
        ),
        ScheduledJob("daily_bulletin", 60.0, bulletin_worker.run_once),
        ScheduledJob(
            "closing_proxy",
            application.settings.live_close_poll_seconds,
            application.live_closing_proxy.run_once,
        ),
        ScheduledJob(
            "monitoring",
            float(lifecycle.monitoring_interval_seconds),
            application.monitoring.worker.run_once,
            has_pending_work=lambda: application.monitoring.worker.has_pending,
        ),
        ScheduledJob(
            "results",
            float(application.settings.application.result_settlement_policy.poll_interval_seconds),
            application.results.worker.run_once,
            has_pending_work=lambda: application.results.worker.has_pending,
        ),
    )

    def degraded(error: BaseException) -> None:
        if isinstance(error, (ApiBudgetExceededError, TransportError)):
            application.provider_state.failure(error)
        state.update(accepting_work=False)

    def recovered() -> None:
        state.update(accepting_work=True, last_scheduler_tick=datetime.now(UTC))

    state.update(scheduler_alive=True, accepting_work=True)
    try:
        return ProductionOrchestrator(
            jobs,
            application.runtime,
            instance_id=instance_id,
            stop=stop,
            tick_seconds=application.settings.scheduler_tick_seconds,
            leader_healthy=leader.healthy,  # type: ignore[attr-defined]
            on_degraded=degraded,
            on_recovered=recovered,
        ).run_forever()
    finally:
        state.update(scheduler_alive=False, accepting_work=False)


def main() -> None:
    if os.getenv("QUANTBET_PROCESS", "worker").strip().lower() == "dashboard":
        from h2h.dashboard_entrypoint import main as dashboard_main

        dashboard_main()
        return
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    settings = load_production_settings()
    stop = Event()
    state = RuntimeHealthState()

    def request_shutdown() -> None:
        state.update(accepting_work=False, leadership="stopping")
        stop.set()
        LOGGER.info(
            "graceful shutdown requested; waiting for bounded in-flight work",
            extra={"shutdown_grace_seconds": settings.shutdown_grace_seconds},
        )

    install_shutdown_handlers(request_shutdown)
    application = build_production_application(settings, should_stop=stop.is_set)
    health: HealthService | None = None
    leader = None
    instance_id = os.getenv("RAILWAY_REPLICA_ID", "").strip() or f"local-{uuid4()}"
    try:
        _connect_with_retry(application, stop)
        application.runtime.verify_schema(_expected_migrations())
        state.update(schema_current=True)
        health = HealthService(application, state, host="0.0.0.0", port=settings.port)
        health.start()
        LOGGER.info("health service started")
        while not stop.is_set():
            leader = application.runtime.open_leader_lock()
            if not leader.try_acquire():
                state.update(leadership="standby", scheduler_alive=False, accepting_work=False)
                leader.close()
                leader = None
                stop.wait(settings.scheduler_tick_seconds)
                continue
            LOGGER.info("production leadership acquired")
            requested_shutdown = _run_active_leader(application, state, stop, leader, instance_id)
            leader.close()
            leader = None
            if requested_shutdown:
                break
            state.update(leadership="standby")
            LOGGER.warning("production leadership lost; returning to standby")
        state.update(leadership="stopping", accepting_work=False)
    finally:
        stop.set()
        if leader is not None:
            leader.close()
        if health is not None:
            health.close()
        application.close()
        LOGGER.info("QuantBet worker stopped")


if __name__ == "__main__":
    main()
