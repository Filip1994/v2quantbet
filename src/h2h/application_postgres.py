"""Composition root for the PostgreSQL-backed historical quote application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Self

from h2h.persistence import PostgreSQLQuoteHistoryRepository
from h2h.use_cases.quote_history import QuoteHistoryIngestionService


@dataclass
class PostgreSQLQuoteHistoryApplication:
    """Own the PostgreSQL history repository and ingestion service."""

    repository: PostgreSQLQuoteHistoryRepository
    service: QuoteHistoryIngestionService

    def close(self) -> None:
        """Release application-owned resources.

        Connections are opened per repository operation, so there is no
        persistent connection to close at this composition layer.
        """

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
