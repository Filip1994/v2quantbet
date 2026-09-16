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
from h2h.persistence.migrations import apply_migrations
from h2h.use_cases.api_football_training import ApiFootballHistoricalResults
from h2h.use_cases.model_lifecycle import (
    ActivateDixonColesModel,
    LoadActiveDixonColesModel,
    TrainApiFootballDixonColesModel,
)
from h2h.use_cases.quote_history import QuoteHistoryIngestionService


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
