"""Single-process production composition for the Railway V1 pilot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from h2h.application import build_api_football_client
from h2h.application_postgres import (
    PostgreSQLPickMonitoringApplication,
    PostgreSQLPickRegistrationApplication,
    PostgreSQLProductionPredictionApplication,
    PostgreSQLResultSettlementApplication,
    build_postgres_pick_monitoring_application,
    build_postgres_pick_registration_application,
    build_postgres_production_prediction_application,
    build_postgres_result_settlement_application,
)
from h2h.config import PilotScope, ProductionSettings
from h2h.odds import ApiFootballOddsService, DailyApiBudget
from h2h.odds.http import UrllibJsonTransport
from h2h.persistence import (
    PostgreSQLActiveDixonColesModelRepository,
    PostgreSQLDixonColesModelVersionRepository,
)
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository
from h2h.use_cases.api_football_fixture_discovery import ApiFootballFixtureDiscovery
from h2h.use_cases.model_lifecycle import LoadActiveDixonColesModel
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.result_settlement import ApiFootballResultSource
from h2h.use_cases.scoped_fixture_discovery import ScopedFixtureDiscovery
from h2h.workers.opportunity import OpportunityWorker, PilotFixtureDiscovery


@dataclass
class ProviderOperationalState:
    last_error_class: str | None = None
    last_error_message: str | None = None
    last_error_at: datetime | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def failure(self, error: BaseException, *, at: datetime | None = None) -> None:
        with self._lock:
            self.last_error_class = type(error).__name__[:100]
            self.last_error_message = " ".join(str(error).split())[:500]
            self.last_error_at = (at or datetime.now(UTC)).astimezone(UTC)

    def clear(self) -> None:
        with self._lock:
            self.last_error_class = None
            self.last_error_message = None
            self.last_error_at = None


@dataclass
class ProductionApplication:
    settings: ProductionSettings
    budget: DailyApiBudget
    client: object
    provider_state: ProviderOperationalState
    runtime: PostgreSQLRuntimeRepository
    prediction: PostgreSQLProductionPredictionApplication
    registration: PostgreSQLPickRegistrationApplication
    monitoring: PostgreSQLPickMonitoringApplication
    results: PostgreSQLResultSettlementApplication
    active_model_loader: LoadActiveDixonColesModel
    opportunity: OpportunityWorker
    usable_scopes: set[PilotScope]

    def close(self) -> None:
        self.prediction.close()
        self.registration.close()
        self.monitoring.close()
        self.results.close()


def build_production_application(
    settings: ProductionSettings,
    *,
    should_stop=lambda: False,
) -> ProductionApplication:
    application_settings = settings.application
    assert application_settings.database_url is not None
    assert application_settings.registration_policy is not None
    assert application_settings.odds_lifecycle_policy is not None

    budget = DailyApiBudget(settings.api_daily_limit, settings.api_reserve)
    client = build_api_football_client(
        UrllibJsonTransport(),
        application_settings,
        budget=budget,
        timeout=settings.api_timeout_seconds,
        should_stop=should_stop,
    )
    source = ApiFootballOddsService(client)
    provider_state = ProviderOperationalState()
    runtime = PostgreSQLRuntimeRepository(application_settings.database_url)

    scoped = ScopedFixtureDiscovery(ApiFootballFixtureDiscovery(client))
    pilot_discovery = PilotFixtureDiscovery(
        scoped, settings.pilot_scopes, settings.pilot_fixture_ids
    )
    prediction = build_postgres_production_prediction_application(
        database_url=application_settings.database_url,
        discovery=pilot_discovery,
    )
    registration = build_postgres_pick_registration_application(
        application_settings.registration_policy,
        database_url=application_settings.database_url,
    )

    def item_failure(worker: str):
        def record(item_id: str, error: BaseException, at: datetime) -> None:
            provider_state.failure(error, at=at)
            runtime.record_item_failure(worker, item_id, error, failed_at=at)

        return record

    def item_success(worker: str):
        def clear(item_id: str) -> None:
            runtime.clear_item_failure(worker, item_id)

        return clear

    monitoring = build_postgres_pick_monitoring_application(
        application_settings.odds_lifecycle_policy,
        source,
        database_url=application_settings.database_url,
        bulletin_timezone=application_settings.bulletin_timezone,
        on_item_failure=item_failure("monitoring"),
        on_item_success=item_success("monitoring"),
        should_stop=should_stop,
    )
    results = build_postgres_result_settlement_application(
        application_settings.result_settlement_policy,
        ApiFootballResultSource(client),
        database_url=application_settings.database_url,
        on_item_failure=item_failure("results"),
        on_item_success=item_success("results"),
        should_stop=should_stop,
    )
    versions = PostgreSQLDixonColesModelVersionRepository(
        database_url=application_settings.database_url
    )
    active = PostgreSQLActiveDixonColesModelRepository(
        database_url=application_settings.database_url
    )
    loader = LoadActiveDixonColesModel(versions, active)
    usable_scopes: set[PilotScope] = set()
    opportunity = OpportunityWorker(
        runtime,
        source,
        QuoteHistoryIngestionService(
            prediction.quote_history, capture_clock=lambda: datetime.now(UTC)
        ),
        prediction.predictor,
        prediction.evaluator,
        registration.register_pick,
        scopes=settings.pilot_scopes,
        bookmaker_id=settings.pilot_bookmaker_id,
        provider_fixture_ids=settings.pilot_fixture_ids,
        allowed_statuses=application_settings.registration_policy.allowed_fixture_statuses,
        usable_scopes=lambda: frozenset(usable_scopes),
        should_stop=should_stop,
    )
    return ProductionApplication(
        settings,
        budget,
        client,
        provider_state,
        runtime,
        prediction,
        registration,
        monitoring,
        results,
        loader,
        opportunity,
        usable_scopes,
    )
