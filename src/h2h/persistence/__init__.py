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
from .postgres_fixtures import PostgreSQLFixtureRepository
from .postgres_predictions import PostgreSQLFixturePredictionRepository
from .postgres_value_evaluations import PostgreSQLValueEvaluationRepository
from .postgres_pick_registration import PostgreSQLPickRegistrationRepository
from .postgres_pick_monitoring import PostgreSQLPickMonitoringRepository
from .postgres_daily_bulletin import PostgreSQLDailyBulletinRepository
from .pick_monitoring import (
    PickClosingNotDueError,
    PickMonitoringConflictError,
    PickMonitoringNotStartedError,
    PickMonitoringRepository,
)
from .pick_registration import (
    BankrollBootstrapConflictError,
    BankrollNotBootstrappedError,
    RegistrationPersistenceConflictError,
    RegistrationProvenanceError,
)
from .fixtures import FixturePersistenceConflictError, FixtureRepository
from .predictions import FixturePredictionRepository, PredictionPersistenceConflictError
from .value_evaluations import (
    ValueEvaluationPersistenceConflictError,
    ValueEvaluationRepository,
)
from .quote_history import (
    InMemoryQuoteHistoryRepository,
    QuoteHistoryConflictError,
    QuoteHistoryRepository,
)
from .quotes import InMemoryQuoteRepository, QuoteRepository
from .sqlite import SQLiteQuoteRepository

__all__ = [
    "ActiveModelUnavailableError",
    "BankrollBootstrapConflictError",
    "BankrollNotBootstrappedError",
    "FixturePersistenceConflictError",
    "FixturePredictionRepository",
    "FixtureRepository",
    "InMemoryQuoteHistoryRepository",
    "InMemoryQuoteRepository",
    "ModelActivationConflictError",
    "ModelPersistenceConflictError",
    "PickClosingNotDueError",
    "PickMonitoringConflictError",
    "PickMonitoringNotStartedError",
    "PickMonitoringRepository",
    "PostgreSQLActiveDixonColesModelRepository",
    "PostgreSQLDailyBulletinRepository",
    "PostgreSQLDixonColesModelVersionRepository",
    "PostgreSQLFixturePredictionRepository",
    "PostgreSQLFixtureRepository",
    "PostgreSQLPickMonitoringRepository",
    "PostgreSQLPickRegistrationRepository",
    "PostgreSQLQuoteHistoryRepository",
    "PostgreSQLValueEvaluationRepository",
    "PredictionPersistenceConflictError",
    "QuoteHistoryConflictError",
    "QuoteHistoryRepository",
    "QuoteRepository",
    "RegistrationPersistenceConflictError",
    "RegistrationProvenanceError",
    "SQLiteQuoteRepository",
    "ValueEvaluationPersistenceConflictError",
    "ValueEvaluationRepository",
    "apply_migrations",
]
