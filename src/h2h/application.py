"""Composition root for the quote application service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from h2h.application_postgres import (
    PostgreSQLQuoteHistoryApplication,
    build_postgres_quote_history_application,
)
from h2h.config import ApplicationSettings
from h2h.odds import ApiFootballClient, BudgetedJsonTransport, DailyApiBudget
from h2h.odds.http import JsonTransport
from h2h.persistence import SQLiteQuoteRepository
from h2h.use_cases import QuoteIngestionService


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
) -> ApiFootballClient:
    """Build an API-Football client protected by a shared daily call budget."""
    budget = DailyApiBudget(daily_limit=daily_limit, reserve=reserve)
    guarded_transport = BudgetedJsonTransport(transport=transport, budget=budget)
    return ApiFootballClient(
        transport=guarded_transport,
        api_key=settings.api_football_key,
    )
