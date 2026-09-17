"""Composition root for the quote application service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self
from collections.abc import Callable

from h2h.application_postgres import (
    PostgreSQLDixonColesModelLifecycleApplication,
    PostgreSQLQuoteHistoryApplication,
    build_postgres_dixon_coles_model_lifecycle_application,
    build_postgres_quote_history_application,
    PostgreSQLProductionPredictionApplication,
    PostgreSQLPickRegistrationApplication,
    PostgreSQLPickMonitoringApplication,
    PostgreSQLResultSettlementApplication,
    build_postgres_pick_monitoring_application,
    build_postgres_pick_registration_application,
    build_postgres_result_settlement_application,
    build_postgres_production_prediction_application,
)
from h2h.config import ApplicationSettings
from h2h.odds import (
    ApiFootballClient,
    ApiFootballOddsService,
    BudgetedJsonTransport,
    DailyApiBudget,
    RetryingJsonTransport,
)
from h2h.odds.api_football_client import API_FOOTBALL_BASE_URL
from h2h.odds.http import JsonTransport, UrllibJsonTransport
from h2h.persistence import SQLiteQuoteRepository
from h2h.use_cases import QuoteIngestionService
from h2h.use_cases.api_football_training import (
    ApiFootballHistoricalResults,
    _trusted_api_football_historical_results,
)
from h2h.use_cases.api_football_fixture_discovery import ApiFootballFixtureDiscovery
from h2h.use_cases.scoped_fixture_discovery import ScopedFixtureDiscovery
from h2h.use_cases.result_settlement import ApiFootballResultSource


@dataclass
class SQLiteQuoteApplication:
    """Own a SQLite repository and its quote application service.

    Legacy compatibility boundary. Production composition must use the
    PostgreSQL application builder below.
    """

    repository: SQLiteQuoteRepository
    service: QuoteIngestionService

    def close(self) -> None:
        """Close the application's SQLite connection."""
        self.repository.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def build_sqlite_quote_application(
    database_path: str | Path,
) -> SQLiteQuoteApplication:
    """Build the legacy SQLite quote application."""
    repository = SQLiteQuoteRepository(database_path)
    return SQLiteQuoteApplication(
        repository=repository,
        service=QuoteIngestionService(repository),
    )


def build_sqlite_quote_application_from_settings(
    settings: ApplicationSettings,
) -> SQLiteQuoteApplication:
    """Build the legacy SQLite application from validated settings."""
    return build_sqlite_quote_application(settings.database_path)


def build_postgres_quote_history_application_from_settings(
    settings: ApplicationSettings,
) -> PostgreSQLQuoteHistoryApplication:
    """Build the production PostgreSQL application from validated settings.

    ``DATABASE_URL`` is mandatory for this path; SQLite settings are not
    consulted and cannot silently become the production persistence backend.
    """
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for PostgreSQL application composition")
    return build_postgres_quote_history_application(database_url=settings.database_url)


def build_sqlite_quote_service(database_path: str | Path) -> QuoteIngestionService:
    """Build the legacy SQLite-backed quote ingestion service."""
    repository = SQLiteQuoteRepository(database_path)
    return QuoteIngestionService(repository)


def build_api_football_client(
    transport: JsonTransport,
    settings: ApplicationSettings,
    *,
    daily_limit: int = 7500,
    reserve: int = 1500,
    budget: DailyApiBudget | None = None,
    timeout: float = 10.0,
    should_stop: Callable[[], bool] = lambda: False,
) -> ApiFootballClient:
    """Build an API-Football client protected by a shared daily call budget."""
    shared_budget = budget or DailyApiBudget(daily_limit=daily_limit, reserve=reserve)
    guarded_transport = BudgetedJsonTransport(transport=transport, budget=shared_budget)
    retrying_transport = RetryingJsonTransport(
        transport=guarded_transport,
        max_attempts=2,
        backoff_seconds=1.0,
        max_backoff_seconds=30.0,
        should_stop=should_stop,
    )
    return ApiFootballClient(
        transport=retrying_transport,
        api_key=settings.api_football_key,
        base_url=API_FOOTBALL_BASE_URL,
        timeout=timeout,
    )


def build_trusted_api_football_historical_results(
    settings: ApplicationSettings,
) -> ApiFootballHistoricalResults:
    """Build the sole supported API-Football training-provenance acquisition path."""
    client = build_api_football_client(UrllibJsonTransport(), settings)
    return _trusted_api_football_historical_results(client)


def build_postgres_dixon_coles_model_lifecycle_from_settings(
    settings: ApplicationSettings,
) -> PostgreSQLDixonColesModelLifecycleApplication:
    """Build the production lifecycle boundary without running training or activation."""
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for model lifecycle composition")
    historical_results = build_trusted_api_football_historical_results(settings)
    return build_postgres_dixon_coles_model_lifecycle_application(
        historical_results,
        database_url=settings.database_url,
    )


def build_postgres_production_prediction_from_settings(
    settings: ApplicationSettings,
) -> PostgreSQLProductionPredictionApplication:
    """Compose provider acquisition around the durable production boundary."""
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for production prediction composition")
    client = build_api_football_client(UrllibJsonTransport(), settings)
    discovery = ScopedFixtureDiscovery(ApiFootballFixtureDiscovery(client))
    return build_postgres_production_prediction_application(
        database_url=settings.database_url,
        discovery=discovery,
    )


def build_postgres_pick_registration_from_settings(
    settings: ApplicationSettings,
) -> PostgreSQLPickRegistrationApplication:
    """Compose Task #10 only from complete durable database and policy settings."""

    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for pick registration composition")
    if settings.registration_policy is None:
        raise ValueError("registration policy configuration is required")
    return build_postgres_pick_registration_application(
        settings.registration_policy,
        database_url=settings.database_url,
    )


def build_postgres_pick_monitoring_from_settings(
    settings: ApplicationSettings,
    *,
    source: ApiFootballOddsService | None = None,
) -> PostgreSQLPickMonitoringApplication:
    """Compose the Task #11 backend worker and read models from explicit settings."""

    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for pick monitoring composition")
    if settings.odds_lifecycle_policy is None:
        raise ValueError("odds lifecycle configuration is required")
    if source is None:
        client = build_api_football_client(UrllibJsonTransport(), settings)
        source = ApiFootballOddsService(client)
    return build_postgres_pick_monitoring_application(
        settings.odds_lifecycle_policy,
        source,
        database_url=settings.database_url,
        bulletin_timezone=settings.bulletin_timezone,
    )


def build_postgres_result_settlement_from_settings(
    settings: ApplicationSettings,
    *,
    client: ApiFootballClient | None = None,
) -> PostgreSQLResultSettlementApplication:
    """Compose Task #12 around the shared V1 provider client."""
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for result settlement composition")
    result_client = client or build_api_football_client(UrllibJsonTransport(), settings)
    return build_postgres_result_settlement_application(
        settings.result_settlement_policy,
        ApiFootballResultSource(result_client),
        database_url=settings.database_url,
    )
