"""Provider-neutral persistence boundaries."""

from .quotes import InMemoryQuoteRepository, QuoteRepository
from .sqlite import SQLiteQuoteRepository

__all__ = ["InMemoryQuoteRepository", "QuoteRepository", "SQLiteQuoteRepository"]
