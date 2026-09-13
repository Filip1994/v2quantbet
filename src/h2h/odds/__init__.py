"""Odds acquisition, normalization and validation."""

from .api_football_adapter import ApiFootballQuoteAdapter
from .provider_adapter import NormalizingProviderQuoteAdapter, ProviderQuoteAdapter
from .snapshot_builder import build_market_snapshot

__all__ = [
    "ApiFootballQuoteAdapter",
    "NormalizingProviderQuoteAdapter",
    "ProviderQuoteAdapter",
    "build_market_snapshot",
]
