"""Tests for the application composition root."""

from pathlib import Path

from h2h.application import build_sqlite_quote_service
from h2h.use_cases import QuoteIngestionService


def test_build_sqlite_quote_service_returns_configured_service(tmp_path: Path) -> None:
    service = build_sqlite_quote_service(tmp_path / "quotes.sqlite3")

    assert isinstance(service, QuoteIngestionService)
    assert service.read_all() == ()
