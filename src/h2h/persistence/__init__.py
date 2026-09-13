"""Provider-neutral persistence boundaries."""

from .quotes import InMemoryQuoteRepository, QuoteRepository

__all__ = ["InMemoryQuoteRepository", "QuoteRepository"]
