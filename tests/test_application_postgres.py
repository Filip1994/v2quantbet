"""Tests for PostgreSQL application composition and lifecycle."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from h2h.application_postgres import (
    PostgreSQLQuoteHistoryApplication,
    build_postgres_quote_history_application,
)
from h2h.persistence import PostgreSQLQuoteHistoryRepository
from h2h.use_cases.quote_history import QuoteHistoryIngestionService


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

    with patch.object(application, "close") as close:
        with application as entered:
            assert entered is application

    close.assert_called_once_with()
