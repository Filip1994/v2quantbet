"""Composition root for the quote application service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from h2h.config import ApplicationSettings
from h2h.persistence import SQLiteQuoteRepository
from h2h.use_cases import QuoteIngestionService


@dataclass
class SQLiteQuoteApplication:
    """Own a SQLite repository and its quote application service."""

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
    """Build a lifecycle-managed SQLite quote application."""
    repository = SQLiteQuoteRepository(database_path)
    return SQLiteQuoteApplication(
        repository=repository,
        service=QuoteIngestionService(repository),
    )


def build_sqlite_quote_application_from_settings(
    settings: ApplicationSettings,
) -> SQLiteQuoteApplication:
    """Build the application from validated infrastructure settings."""
    return build_sqlite_quote_application(settings.database_path)


def build_sqlite_quote_service(database_path: str | Path) -> QuoteIngestionService:
    """Build the application service backed by a SQLite quote repository."""
    repository = SQLiteQuoteRepository(database_path)
    return QuoteIngestionService(repository)
