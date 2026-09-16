"""Tests for PostgreSQL application composition and lifecycle."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from h2h.application_postgres import (
    PostgreSQLPickRegistrationApplication,
    PostgreSQLProductionPredictionApplication,
    PostgreSQLQuoteHistoryApplication,
    build_postgres_production_prediction_application,
    build_postgres_pick_registration_application,
    build_postgres_quote_history_application,
    build_postgres_pick_monitoring_application,
)
from tests.domain.test_task10_policy import policy
from h2h.domain.pick_monitoring import OddsLifecyclePolicy
from h2h.persistence import (
    PostgreSQLFixturePredictionRepository,
    PostgreSQLFixtureRepository,
    PostgreSQLQuoteHistoryRepository,
    PostgreSQLValueEvaluationRepository,
)
from h2h.use_cases.production_prediction import ProduceFixturePrediction
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.value_evaluation import EvaluatePersistedPredictionQuote


def test_builder_creates_postgresql_repository_and_ingestion_service() -> None:
    application = build_postgres_quote_history_application(
        database_url="postgresql://example.invalid/quantbet"
    )

    assert isinstance(application, PostgreSQLQuoteHistoryApplication)
    assert isinstance(application.repository, PostgreSQLQuoteHistoryRepository)
    assert isinstance(application.service, QuoteHistoryIngestionService)


def test_migrate_uses_repository_connection_and_migration_directory(
    tmp_path: Path,
) -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    repository = Mock()
    repository.connect.return_value = connection
    application = PostgreSQLQuoteHistoryApplication(repository=repository, service=Mock())

    with patch("h2h.application_postgres.apply_migrations", return_value=("001_quote_history.sql",)) as migrate:
        result = application.migrate(tmp_path)

    assert result == ("001_quote_history.sql",)
    repository.connect.assert_called_once_with()
    migrate.assert_called_once_with(connection, tmp_path)
    connection.__exit__.assert_called_once()


def test_migrate_uses_default_directory_when_not_provided() -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    repository = Mock()
    repository.connect.return_value = connection
    application = PostgreSQLQuoteHistoryApplication(repository=repository, service=Mock())

    with patch("h2h.application_postgres.apply_migrations", return_value=()) as migrate:
        assert application.migrate() == ()

    migrate.assert_called_once()
    assert migrate.call_args.args[0] is connection
    assert migrate.call_args.args[1].name == "migrations"


def test_close_is_safe_when_repository_connections_are_operation_scoped() -> None:
    repository = Mock()
    application = PostgreSQLQuoteHistoryApplication(repository=repository, service=Mock())

    application.close()

    repository.connect.assert_not_called()


def test_context_manager_calls_close() -> None:
    application = PostgreSQLQuoteHistoryApplication(repository=Mock(), service=Mock())

    with patch.object(application, "close") as close, application as entered:
        assert entered is application

    close.assert_called_once_with()


def test_production_builder_wires_durable_repositories_and_pure_use_cases() -> None:
    application = build_postgres_production_prediction_application(
        database_url="postgresql://example.invalid/quantbet"
    )

    assert isinstance(application, PostgreSQLProductionPredictionApplication)
    assert isinstance(application.fixtures, PostgreSQLFixtureRepository)
    assert isinstance(application.predictions, PostgreSQLFixturePredictionRepository)
    assert isinstance(application.evaluations, PostgreSQLValueEvaluationRepository)
    assert isinstance(application.quote_history, PostgreSQLQuoteHistoryRepository)
    assert isinstance(application.predictor, ProduceFixturePrediction)
    assert isinstance(application.evaluator, EvaluatePersistedPredictionQuote)
    assert application.durable_discovery is None


def test_pick_registration_builder_has_no_bootstrap_side_effect() -> None:
    application = build_postgres_pick_registration_application(
        policy(), database_url="postgresql://example.invalid/quantbet"
    )
    assert isinstance(application, PostgreSQLPickRegistrationApplication)
    assert application.register_pick is not None
    assert application.bootstrap_bankroll is not None


def test_pick_monitoring_builder_wires_worker_and_bulletin() -> None:
    source = Mock()
    application = build_postgres_pick_monitoring_application(
        OddsLifecyclePolicy(300, 600, 900),
        source,
        database_url="postgresql://example.invalid/quantbet",
    )
    assert application.worker is not None
    assert application.read_lifecycle is not None
    assert application.bulletin.timezone.key == "Europe/Belgrade"
