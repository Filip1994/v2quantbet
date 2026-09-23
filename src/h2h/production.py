"""Single-process production composition for the Phase I football universe."""

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
from h2h.config import ProductionSettings
from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.odds import ApiFootballOddsService, PostgreSQLApiBudget
from h2h.odds.http import UrllibJsonTransport
from h2h.persistence import (
    PostgreSQLActiveDixonColesModelRepository,
    PostgreSQLDixonColesModelVersionRepository,
)
from h2h.persistence.postgres_runtime import OpportunityFixture, PostgreSQLRuntimeRepository
from h2h.persistence.postgres_model_coverage import PostgreSQLModelCoverageRepository
from h2h.use_cases.api_football_training import _trusted_api_football_historical_results
from h2h.use_cases.api_football_fixture_discovery import ApiFootballFixtureDiscovery
from h2h.use_cases.model_lifecycle import (
    ActivateDixonColesModel,
    LoadActiveDixonColesModel,
    TrainApiFootballDixonColesModel,
)
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.result_settlement import ApiFootballResultSource
from h2h.use_cases.scoped_fixture_discovery import ScopedFixtureDiscovery
from h2h.workers.opportunity import OpportunityWorker
from h2h.workers.model_lifecycle import ModelLifecycleWorker


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
    budget: PostgreSQLApiBudget
    client: object
    provider_state: ProviderOperationalState
    runtime: PostgreSQLRuntimeRepository
    prediction: PostgreSQLProductionPredictionApplication
    registration: PostgreSQLPickRegistrationApplication
    monitoring: PostgreSQLPickMonitoringApplication
    results: PostgreSQLResultSettlementApplication
    active_model_loader: LoadActiveDixonColesModel
    model_coverage: PostgreSQLModelCoverageRepository
    model_lifecycle: ModelLifecycleWorker
    opportunity: OpportunityWorker

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

    runtime = PostgreSQLRuntimeRepository(application_settings.database_url)
    budget = PostgreSQLApiBudget(
        daily_limit=settings.api_daily_limit,
        reserve=settings.api_reserve,
        training_daily_limit=settings.model_training_daily_limit,
        operational_reserve=settings.model_training_operational_reserve,
        database_url=application_settings.database_url,
    )
    client = build_api_football_client(
        UrllibJsonTransport(),
        application_settings,
        budget=budget,
        timeout=settings.api_timeout_seconds,
        should_stop=should_stop,
    )
    source = ApiFootballOddsService(client)
    provider_state = ProviderOperationalState()

    scoped = ScopedFixtureDiscovery(ApiFootballFixtureDiscovery(client))
    prediction = build_postgres_production_prediction_application(
        database_url=application_settings.database_url,
        discovery=scoped,
    )
    registration = build_postgres_pick_registration_application(
        application_settings.registration_policy,
        database_url=application_settings.database_url,
        require_final_quote_verification=True,
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

    monitoring_client = build_api_football_client(
        UrllibJsonTransport(),
        application_settings,
        budget=budget,
        timeout=settings.api_timeout_seconds,
        should_stop=should_stop,
        odds_request_category="results_monitoring",
    )
    monitoring = build_postgres_pick_monitoring_application(
        application_settings.odds_lifecycle_policy,
        ApiFootballOddsService(monitoring_client),
        database_url=application_settings.database_url,
        bulletin_timezone=application_settings.bulletin_timezone,
        on_item_failure=item_failure("monitoring"),
        on_item_success=item_success("monitoring"),
        should_stop=should_stop,
    )
    results = build_postgres_result_settlement_application(
        application_settings.result_settlement_policy,
        ApiFootballResultSource(monitoring_client),
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
    coverage = PostgreSQLModelCoverageRepository(database_url=application_settings.database_url)
    training_client = build_api_football_client(
        UrllibJsonTransport(),
        application_settings,
        budget=budget,
        timeout=settings.api_timeout_seconds,
        should_stop=should_stop,
    )
    historical = _trusted_api_football_historical_results(
        training_client,
        load_cached_payload=coverage.load_acquisition,
        save_cached_payload=coverage.save_acquisition,
    )
    trainer = TrainApiFootballDixonColesModel(
        historical,
        versions,
        clock=lambda: datetime.now(UTC),
    )
    activator = ActivateDixonColesModel(
        versions,
        active,
        clock=lambda: datetime.now(UTC),
    )
    model_lifecycle = ModelLifecycleWorker(
        coverage,
        trainer,
        activator,
        active,
        settings.model_training_policy,
        max_scopes=settings.model_training_max_scopes,
        max_provider_requests=settings.model_training_max_provider_requests,
        max_wall_seconds=settings.model_training_max_wall_seconds,
        training_requests_used=lambda: budget.usage_by_category()["model_training"],
        should_stop=should_stop,
    )

    def ensure_model_available(fixture: OpportunityFixture) -> None:
        loader.execute_with_selection(
            DixonColesModelScope(
                provider="api-football",
                team_id_namespace="api-football",
                league_id=fixture.league_id,
                season=fixture.season,
            )
        )

    opportunity = OpportunityWorker(
        runtime,
        source,
        QuoteHistoryIngestionService(
            prediction.quote_history, capture_clock=lambda: datetime.now(UTC)
        ),
        prediction.predictor,
        prediction.evaluator,
        registration.register_pick,
        bookmaker_id=settings.bookmaker_id,
        allowed_statuses=application_settings.registration_policy.allowed_fixture_statuses,
        ensure_model_available=ensure_model_available,
        should_stop=should_stop,
        model_scope_status=lambda fixture: (
            status
            if (
                status := coverage.opportunity_status(
                    DixonColesModelScope(
                        "api-football",
                        "api-football",
                        fixture.league_id,
                        fixture.season,
                    )
                )
            )
            is not None
            else None
        ),
        max_items=settings.opportunity_max_items,
        max_wall_seconds=settings.opportunity_max_wall_seconds,
        maximum_quote_age_seconds=(
            application_settings.registration_policy.maximum_quote_age_seconds
        ),
        minimum_time_to_kickoff_seconds=(
            application_settings.registration_policy.minimum_time_to_kickoff_seconds
        ),
        stale_retry_policy=settings.stale_quote_retry_policy,
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
        coverage,
        model_lifecycle,
        opportunity,
    )
