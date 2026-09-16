"""Tests for the application composition root."""

import sqlite3
from pathlib import Path
from unittest.mock import Mock

from h2h.application import (
    build_api_football_client,
    build_postgres_dixon_coles_model_lifecycle_from_settings,
    build_sqlite_quote_application,
    build_sqlite_quote_application_from_settings,
    build_sqlite_quote_service,
)
from h2h.application_postgres import PostgreSQLDixonColesModelLifecycleApplication
from h2h.config import ApplicationSettings
from h2h.odds import ApiBudgetExceededError
from h2h.use_cases import QuoteIngestionService


def test_build_sqlite_quote_service_returns_configured_service(tmp_path: Path) -> None:
    service = build_sqlite_quote_service(tmp_path / "quotes.sqlite3")

    assert isinstance(service, QuoteIngestionService)
    assert service.read_all() == ()


def test_application_context_manager_closes_repository(tmp_path: Path) -> None:
    with build_sqlite_quote_application(tmp_path / "quotes.sqlite3") as application:
        assert isinstance(application.service, QuoteIngestionService)
        assert application.service.read_all() == ()
        repository = application.repository

    try:
        repository.all()
    except sqlite3.ProgrammingError:
        pass
    else:
        raise AssertionError("repository should be closed after context exit")


def test_closed_application_database_can_be_reopened(tmp_path: Path) -> None:
    database_path = tmp_path / "quotes.sqlite3"

    with build_sqlite_quote_application(database_path):
        pass

    reopened = build_sqlite_quote_application(database_path)
    try:
        assert reopened.service.read_all() == ()
    finally:
        reopened.close()


def test_build_application_from_settings_uses_database_path(tmp_path: Path) -> None:
    settings = ApplicationSettings(
        database_path=tmp_path / "configured.sqlite3",
        api_football_key="test-only-key",
    )

    with build_sqlite_quote_application_from_settings(settings) as application:
        assert application.service.read_all() == ()
    assert settings.api_football_key == "test-only-key"


def test_build_api_football_client_enforces_daily_budget() -> None:
    transport = Mock()
    transport.get_json.return_value = {"response": []}
    settings = ApplicationSettings(
        database_path=Path("quotes.sqlite3"),
        api_football_key="test-only-key",
    )

    client = build_api_football_client(transport, settings, daily_limit=1, reserve=0)
    client.fetch_odds(fixture_id=101)

    try:
        client.fetch_odds(fixture_id=102)
    except ApiBudgetExceededError:
        pass
    else:
        raise AssertionError("client should enforce the daily API budget")

    assert transport.get_json.call_count == 1


def test_model_lifecycle_composition_requires_postgres_and_has_no_side_effects() -> None:
    missing = ApplicationSettings(
        database_path=Path("unused.sqlite3"),
        api_football_key="test-only-key",
    )
    try:
        build_postgres_dixon_coles_model_lifecycle_from_settings(missing)
    except ValueError as exc:
        assert "DATABASE_URL" in str(exc)
    else:
        raise AssertionError("model lifecycle composition must require DATABASE_URL")

    configured = ApplicationSettings(
        database_path=Path("unused.sqlite3"),
        api_football_key="test-only-key",
        database_url="postgresql://example.invalid/quantbet",
    )
    application = build_postgres_dixon_coles_model_lifecycle_from_settings(configured)
    assert isinstance(application, PostgreSQLDixonColesModelLifecycleApplication)
    assert application.trainer is not None
    assert application.activator is not None
    assert application.loader is not None
