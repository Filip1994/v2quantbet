"""Provider-neutral persistence boundaries."""

from .migrations import apply_migrations
from .model_lifecycle import (
    ActiveModelUnavailableError,
    ModelActivationConflictError,
    ModelPersistenceConflictError,
)
from .postgres_model_lifecycle import (
    PostgreSQLActiveDixonColesModelRepository,
    PostgreSQLDixonColesModelVersionRepository,
)
from .postgres_quote_history import PostgreSQLQuoteHistoryRepository
from .quote_history import (
    InMemoryQuoteHistoryRepository,
    QuoteHistoryConflictError,
    QuoteHistoryRepository,
)
from .quotes import InMemoryQuoteRepository, QuoteRepository
from .sqlite import SQLiteQuoteRepository

__all__ = [
    "ActiveModelUnavailableError",
    "InMemoryQuoteHistoryRepository",
    "InMemoryQuoteRepository",
    "ModelActivationConflictError",
    "ModelPersistenceConflictError",
    "PostgreSQLActiveDixonColesModelRepository",
    "PostgreSQLDixonColesModelVersionRepository",
    "PostgreSQLQuoteHistoryRepository",
    "QuoteHistoryConflictError",
    "QuoteHistoryRepository",
    "QuoteRepository",
    "SQLiteQuoteRepository",
    "apply_migrations",
]
