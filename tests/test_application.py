"""Tests for the application composition root."""

import sqlite3
from pathlib import Path

from h2h.application import (
    build_sqlite_quote_application,
    build_sqlite_quote_service,
)
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
