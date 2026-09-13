"""Odds acquisition, normalization and validation."""

from .api_football_adapter import ApiFootballQuoteAdapter
from .api_football_ingestion import (
    build_api_football_market_snapshots,
    ingest_api_football_odds,
    iter_api_football_quote_payloads,
)
from .provider_adapter import NormalizingProviderQuoteAdapter, ProviderQuoteAdapter
from .quote_deduplication import QuoteConflictError, deduplicate_quotes
from .snapshot_builder import build_market_snapshot

__all__ = [
    "ApiFootballQuoteAdapter",
    "NormalizingProviderQuoteAdapter",
    "ProviderQuoteAdapter",
    "QuoteConflictError",
    "build_api_football_market_snapshots",
    "build_market_snapshot",
    "deduplicate_quotes",
    "ingest_api_football_odds",
    "iter_api_football_quote_payloads",
]
