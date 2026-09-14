"""Composition root for the quote application service."""

from __future__ import annotations

from pathlib import Path

from h2h.persistence import SQLiteQuoteRepository
from h2h.use_cases import QuoteIngestionService


def build_sqlite_quote_service(database_path: str | Path) -> QuoteIngestionService:
    """Build the application service backed by a SQLite quote repository."""
    repository = SQLiteQuoteRepository(database_path)
    return QuoteIngestionService(repository)
