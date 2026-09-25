"""Composition root for bankroll-free exposure research tracking."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from h2h.domain.pick_monitoring import OddsLifecyclePolicy
from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.persistence import PostgreSQLQuoteHistoryRepository
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository
from h2h.use_cases.pick_monitoring import (
    ReconcileRegisteredPickMonitoring,
    RefreshRegisteredPickOdds,
    RegisteredPickQuoteSource,
)
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.research_signals import RecordExposureBlockedResearchSignal
from h2h.workers.research_signal_monitoring import ResearchSignalMonitoringWorker


@dataclass
class PostgreSQLResearchSignalApplication:
    repository: PostgreSQLResearchSignalRepository
    record_exposure_blocked: RecordExposureBlockedResearchSignal
    reconcile: ReconcileRegisteredPickMonitoring
    refresh_odds: RefreshRegisteredPickOdds
    worker: ResearchSignalMonitoringWorker

    def close(self) -> None:
        """Connections are operation-scoped."""


def build_postgres_research_signal_application(
    registration_policy: RegistrationPolicyConfig,
    lifecycle_policy: OddsLifecyclePolicy,
    source: RegisteredPickQuoteSource,
    database_url: str | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    on_item_failure: Callable[[str, BaseException, datetime], None] | None = None,
    on_item_success: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> PostgreSQLResearchSignalApplication:
    if not isinstance(registration_policy, RegistrationPolicyConfig):
        raise TypeError("registration_policy must be a RegistrationPolicyConfig")
    if not isinstance(lifecycle_policy, OddsLifecyclePolicy):
        raise TypeError("lifecycle_policy must be an OddsLifecyclePolicy")
    research_clock = clock or (lambda: datetime.now(timezone.utc))
    repository = PostgreSQLResearchSignalRepository(database_url=database_url)
    quote_history = PostgreSQLQuoteHistoryRepository(database_url=database_url)
    ingestion = QuoteHistoryIngestionService(quote_history, capture_clock=research_clock)
    recorder = RecordExposureBlockedResearchSignal(
        repository,
        registration_policy,
        clock=research_clock,
    )
    refresh = RefreshRegisteredPickOdds(
        repository,
        source,
        ingestion,
        clock=research_clock,
        claim_limit=10,
        on_item_failure=on_item_failure,
        on_item_success=on_item_success,
        should_stop=should_stop,
    )
    reconcile = ReconcileRegisteredPickMonitoring(
        repository,
        lifecycle_policy,
        clock=research_clock,
    )
    return PostgreSQLResearchSignalApplication(
        repository=repository,
        record_exposure_blocked=recorder,
        reconcile=reconcile,
        refresh_odds=refresh,
        worker=ResearchSignalMonitoringWorker(reconcile, refresh),
    )
