"""Composition root for the PostgreSQL-backed historical quote application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Self

from h2h.persistence import (
    PostgreSQLActiveDixonColesModelRepository,
    PostgreSQLDixonColesModelVersionRepository,
    PostgreSQLQuoteHistoryRepository,
)
from h2h.persistence.postgres_fixtures import PostgreSQLFixtureRepository
from h2h.persistence.postgres_predictions import PostgreSQLFixturePredictionRepository
from h2h.persistence.postgres_value_evaluations import PostgreSQLValueEvaluationRepository
from h2h.persistence.postgres_pick_registration import PostgreSQLPickRegistrationRepository
from h2h.persistence.postgres_pick_monitoring import PostgreSQLPickMonitoringRepository
from h2h.persistence.postgres_daily_bulletin import PostgreSQLDailyBulletinRepository
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository
from h2h.persistence.postgres_performance import PostgreSQLPerformanceRepository
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository
from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.domain.pick_monitoring import OddsLifecyclePolicy
from h2h.domain.settlement import ResultSettlementPolicy
from h2h.persistence.migrations import apply_migrations
from h2h.use_cases.api_football_training import ApiFootballHistoricalResults
from h2h.use_cases.model_lifecycle import (
    ActivateDixonColesModel,
    LoadActiveDixonColesModel,
    TrainApiFootballDixonColesModel,
)
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.durable_fixture_discovery import DurableFixtureDiscovery
from h2h.use_cases.fixture_discovery import FixtureDiscovery
from h2h.use_cases.production_prediction import ProduceFixturePrediction
from h2h.use_cases.value_evaluation import EvaluatePersistedPredictionQuote
from h2h.use_cases.register_pick import BootstrapBankroll, RegisterEligiblePick
from h2h.use_cases.pick_monitoring import (
    FinalizePickClosingOdds,
    ReadPickOddsLifecycle,
    ReconcileRegisteredPickMonitoring,
    RefreshRegisteredPickOdds,
    RegisteredPickQuoteSource,
    StartRegisteredPickMonitoring,
)
from h2h.read_models.daily_bulletin import DailyBulletin
from h2h.workers.registered_pick_monitoring import RegisteredPickMonitoringWorker
from h2h.use_cases.result_settlement import ApiFootballResultSource, ReconcileFixtureResults
from h2h.workers.result_settlement import ResultSettlementWorker
from zoneinfo import ZoneInfo


_DEFAULT_MIGRATION_DIR = Path(__file__).resolve().parents[2] / "migrations"


@dataclass
class PostgreSQLQuoteHistoryApplication:
    """Own the PostgreSQL history repository and ingestion service."""

    repository: PostgreSQLQuoteHistoryRepository
    service: QuoteHistoryIngestionService

    def migrate(self, migration_dir: str | Path = _DEFAULT_MIGRATION_DIR) -> tuple[str, ...]:
        """Apply pending database migrations using the repository connection factory."""
        with self.repository.connect() as connection:
            return apply_migrations(connection, migration_dir)

    def close(self) -> None:
        """Release application-owned resources.

        Connections are opened per repository operation, so there is no
        persistent connection to close at this composition layer.
        """

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


@dataclass
class PostgreSQLDixonColesModelLifecycleApplication:
    """Own the synchronous PostgreSQL-backed model lifecycle services."""

    versions: PostgreSQLDixonColesModelVersionRepository
    active_models: PostgreSQLActiveDixonColesModelRepository
    trainer: TrainApiFootballDixonColesModel
    activator: ActivateDixonColesModel
    loader: LoadActiveDixonColesModel

    def migrate(self, migration_dir: str | Path = _DEFAULT_MIGRATION_DIR) -> tuple[str, ...]:
        with self.versions.connect() as connection:
            return apply_migrations(connection, migration_dir)

    def close(self) -> None:
        """Connections are opened per operation; no persistent resource is owned."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


@dataclass
class PostgreSQLProductionPredictionApplication:
    fixtures: PostgreSQLFixtureRepository
    predictions: PostgreSQLFixturePredictionRepository
    evaluations: PostgreSQLValueEvaluationRepository
    quote_history: PostgreSQLQuoteHistoryRepository
    predictor: ProduceFixturePrediction
    evaluator: EvaluatePersistedPredictionQuote
    durable_discovery: DurableFixtureDiscovery | None

    def migrate(self, migration_dir: str | Path = _DEFAULT_MIGRATION_DIR) -> tuple[str, ...]:
        with self.fixtures.connect() as connection:
            return apply_migrations(connection, migration_dir)

    def close(self) -> None:
        """Connections are opened per operation; no persistent resource is owned."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


@dataclass
class PostgreSQLPickRegistrationApplication:
    repository: PostgreSQLPickRegistrationRepository
    register_pick: RegisterEligiblePick
    bootstrap_bankroll: BootstrapBankroll

    def migrate(self, migration_dir: str | Path = _DEFAULT_MIGRATION_DIR) -> tuple[str, ...]:
        with self.repository.connect() as connection:
            return apply_migrations(connection, migration_dir)

    def close(self) -> None:
        """Connections are operation-scoped."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


@dataclass
class PostgreSQLPickMonitoringApplication:
    repository: PostgreSQLPickMonitoringRepository
    start_monitoring: StartRegisteredPickMonitoring
    refresh_odds: RefreshRegisteredPickOdds
    finalize_closing: FinalizePickClosingOdds
    reconcile: ReconcileRegisteredPickMonitoring
    read_lifecycle: ReadPickOddsLifecycle
    bulletin: DailyBulletin
    worker: RegisteredPickMonitoringWorker

    def migrate(self, migration_dir: str | Path = _DEFAULT_MIGRATION_DIR) -> tuple[str, ...]:
        with self.repository.connect() as connection:
            return apply_migrations(connection, migration_dir)

    def close(self) -> None:
        """Connections are operation-scoped."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


@dataclass
class PostgreSQLResultSettlementApplication:
    repository: PostgreSQLResultSettlementRepository
    performance: PostgreSQLPerformanceRepository
    reconcile: ReconcileFixtureResults
    worker: ResultSettlementWorker

    def migrate(self, migration_dir: str | Path = _DEFAULT_MIGRATION_DIR) -> tuple[str, ...]:
        with self.repository.connect() as connection:
            return apply_migrations(connection, migration_dir)

    def close(self) -> None:
        """Connections are operation-scoped."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def build_postgres_quote_history_application(
    database_url: str | None = None,
    *,
    capture_clock: Callable[[], datetime] | None = None,
) -> PostgreSQLQuoteHistoryApplication:
    """Build the history-aware application backed by PostgreSQL."""
    repository = PostgreSQLQuoteHistoryRepository(database_url=database_url)
    clock = capture_clock or (lambda: datetime.now(timezone.utc))
    return PostgreSQLQuoteHistoryApplication(
        repository=repository,
        service=QuoteHistoryIngestionService(repository, capture_clock=clock),
    )


def build_postgres_dixon_coles_model_lifecycle_application(
    historical_results: ApiFootballHistoricalResults,
    database_url: str | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
) -> PostgreSQLDixonColesModelLifecycleApplication:
    """Build callable lifecycle services without scheduling or activation side effects."""
    lifecycle_clock = clock or (lambda: datetime.now(timezone.utc))
    versions = PostgreSQLDixonColesModelVersionRepository(database_url=database_url)
    active_models = PostgreSQLActiveDixonColesModelRepository(database_url=database_url)
    return PostgreSQLDixonColesModelLifecycleApplication(
        versions=versions,
        active_models=active_models,
        trainer=TrainApiFootballDixonColesModel(
            historical_results,
            versions,
            clock=lifecycle_clock,
        ),
        activator=ActivateDixonColesModel(
            versions,
            active_models,
            clock=lifecycle_clock,
        ),
        loader=LoadActiveDixonColesModel(versions, active_models),
    )


def build_postgres_production_prediction_application(
    database_url: str | None = None,
    *,
    discovery: FixtureDiscovery | None = None,
    clock: Callable[[], datetime] | None = None,
) -> PostgreSQLProductionPredictionApplication:
    """Build the durable production prediction/evaluation path without executing it."""
    production_clock = clock or (lambda: datetime.now(timezone.utc))
    fixtures = PostgreSQLFixtureRepository(database_url=database_url)
    predictions = PostgreSQLFixturePredictionRepository(database_url=database_url)
    evaluations = PostgreSQLValueEvaluationRepository(database_url=database_url)
    quote_history = PostgreSQLQuoteHistoryRepository(database_url=database_url)
    versions = PostgreSQLDixonColesModelVersionRepository(database_url=database_url)
    active_models = PostgreSQLActiveDixonColesModelRepository(database_url=database_url)
    loader = LoadActiveDixonColesModel(versions, active_models)
    return PostgreSQLProductionPredictionApplication(
        fixtures=fixtures,
        predictions=predictions,
        evaluations=evaluations,
        quote_history=quote_history,
        predictor=ProduceFixturePrediction(fixtures, loader, predictions, clock=production_clock),
        evaluator=EvaluatePersistedPredictionQuote(
            predictions, quote_history, evaluations, clock=production_clock
        ),
        durable_discovery=(
            None
            if discovery is None
            else DurableFixtureDiscovery(discovery, fixtures, clock=production_clock)
        ),
    )


def build_postgres_pick_registration_application(
    policy: RegistrationPolicyConfig,
    database_url: str | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    require_final_quote_verification: bool = False,
) -> PostgreSQLPickRegistrationApplication:
    """Build the durable Task #10 boundary without bootstrap or registration side effects."""

    if not isinstance(policy, RegistrationPolicyConfig):
        raise TypeError("policy must be a RegistrationPolicyConfig")
    registration_clock = clock or (lambda: datetime.now(timezone.utc))
    repository = PostgreSQLPickRegistrationRepository(database_url=database_url)
    return PostgreSQLPickRegistrationApplication(
        repository=repository,
        register_pick=RegisterEligiblePick(
            repository,
            policy,
            clock=registration_clock,
            require_final_quote_verification=require_final_quote_verification,
        ),
        bootstrap_bankroll=BootstrapBankroll(repository, policy, clock=registration_clock),
    )


def build_postgres_pick_monitoring_application(
    policy: OddsLifecyclePolicy,
    source: RegisteredPickQuoteSource,
    database_url: str | None = None,
    *,
    bulletin_timezone: ZoneInfo | None = None,
    clock: Callable[[], datetime] | None = None,
    on_item_failure: Callable[[str, BaseException, datetime], None] | None = None,
    on_item_success: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> PostgreSQLPickMonitoringApplication:
    """Compose durable monitoring, finalization, worker, and read-only Bulletin."""

    if not isinstance(policy, OddsLifecyclePolicy):
        raise TypeError("policy must be an OddsLifecyclePolicy")
    lifecycle_clock = clock or (lambda: datetime.now(timezone.utc))
    repository = PostgreSQLPickMonitoringRepository(database_url=database_url)
    quote_history = PostgreSQLQuoteHistoryRepository(database_url=database_url)
    ingestion = QuoteHistoryIngestionService(quote_history, capture_clock=lifecycle_clock)
    start = StartRegisteredPickMonitoring(repository, policy, clock=lifecycle_clock)
    refresh = RefreshRegisteredPickOdds(
        repository,
        source,
        ingestion,
        clock=lifecycle_clock,
        on_item_failure=on_item_failure,
        on_item_success=on_item_success,
        should_stop=should_stop,
    )
    finalize = FinalizePickClosingOdds(repository, clock=lifecycle_clock)
    reconcile = ReconcileRegisteredPickMonitoring(repository, policy, clock=lifecycle_clock)
    read = ReadPickOddsLifecycle(repository, clock=lifecycle_clock)
    bulletin_repository = PostgreSQLDailyBulletinRepository(repository)
    return PostgreSQLPickMonitoringApplication(
        repository=repository,
        start_monitoring=start,
        refresh_odds=refresh,
        finalize_closing=finalize,
        reconcile=reconcile,
        read_lifecycle=read,
        bulletin=DailyBulletin(
            bulletin_repository,
            bulletin_timezone or ZoneInfo("Europe/Belgrade"),
        ),
        worker=RegisteredPickMonitoringWorker(reconcile, refresh),
    )


def build_postgres_result_settlement_application(
    policy: ResultSettlementPolicy,
    source: ApiFootballResultSource,
    database_url: str | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    on_item_failure: Callable[[str, BaseException, datetime], None] | None = None,
    on_item_success: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] = lambda: False,
    research: PostgreSQLResearchSignalRepository | None = None,
) -> PostgreSQLResultSettlementApplication:
    if not isinstance(policy, ResultSettlementPolicy):
        raise TypeError("policy must be a ResultSettlementPolicy")
    result_clock = clock or (lambda: datetime.now(timezone.utc))
    repository = PostgreSQLResultSettlementRepository(policy, database_url=database_url)
    performance = PostgreSQLPerformanceRepository(database_url=database_url)
    reconcile = ReconcileFixtureResults(
        repository,
        source,
        research=research,
        clock=result_clock,
        on_item_failure=on_item_failure,
        on_item_success=on_item_success,
        should_stop=should_stop,
    )
    return PostgreSQLResultSettlementApplication(
        repository=repository,
        performance=performance,
        reconcile=reconcile,
        worker=ResultSettlementWorker(reconcile),
    )