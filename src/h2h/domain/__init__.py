"""Canonical domain objects for fixtures, markets, quotes, and snapshots."""

from .fixture import Fixture
from .fixture_identity import (
    ProviderFixtureReference,
    ResolvedFixtureIdentity,
    api_football_fixture_identity,
    api_football_provider_fixture_id,
)
from .market_snapshot import MarketSnapshot
from .odds import CanonicalQuote, Market, Selection
from .pick_registration import PickRegistration, PickStatus
from .prediction import FixturePrediction, PredictionTarget
from .quote_history import QuoteSeries, QuoteSnapshot
from .quote_normalizer import QuoteNormalizationError, normalize_quote
from .quote_validation import validate_quotes

__all__ = [
    "CanonicalQuote",
    "Fixture",
    "FixturePrediction",
    "Market",
    "MarketSnapshot",
    "PickRegistration",
    "PickStatus",
    "PredictionTarget",
    "ProviderFixtureReference",
    "QuoteNormalizationError",
    "QuoteSeries",
    "QuoteSnapshot",
    "ResolvedFixtureIdentity",
    "Selection",
    "api_football_fixture_identity",
    "api_football_provider_fixture_id",
    "normalize_quote",
    "validate_quotes",
]
