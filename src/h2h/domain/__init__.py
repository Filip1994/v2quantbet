"""Canonical domain objects for fixtures, markets, quotes, and snapshots."""

from .fixture import Fixture
from .fixture_record import FixtureIdentityRecord, FixtureObservation, PersistedFixture
from .fixture_identity import (
    ProviderFixtureReference,
    ResolvedFixtureIdentity,
    api_football_fixture_identity,
    api_football_provider_fixture_id,
)
from .market_snapshot import MarketSnapshot
from .model_lifecycle import (
    ActiveDixonColesModel,
    DixonColesModelArtifact,
    DixonColesModelScope,
    DixonColesModelVersion,
    DixonColesTrainingConfig,
    DixonColesTrainingProvenance,
    LoadedDixonColesModelVersion,
    ValidatedActiveDixonColesModel,
)
from .odds import CanonicalQuote, Market, Selection
from .pick_registration import PickRegistration, PickStatus
from .prediction import FixturePrediction, PredictionTarget
from .prediction_record import PersistedFixturePrediction
from .quote_history import QuoteSeries, QuoteSnapshot
from .quote_normalizer import QuoteNormalizationError, normalize_quote
from .quote_validation import validate_quotes
from .value_evaluation import (
    PROPORTIONAL_TWO_WAY_V1,
    PersistedMarketObservation,
    PersistedQuoteObservation,
    ValueEvaluation,
)

__all__ = [
    "PROPORTIONAL_TWO_WAY_V1",
    "ActiveDixonColesModel",
    "CanonicalQuote",
    "DixonColesModelArtifact",
    "DixonColesModelScope",
    "DixonColesModelVersion",
    "DixonColesTrainingConfig",
    "DixonColesTrainingProvenance",
    "Fixture",
    "FixtureIdentityRecord",
    "FixtureObservation",
    "FixturePrediction",
    "LoadedDixonColesModelVersion",
    "Market",
    "MarketSnapshot",
    "PersistedFixture",
    "PersistedFixturePrediction",
    "PersistedMarketObservation",
    "PersistedQuoteObservation",
    "PickRegistration",
    "PickStatus",
    "PredictionTarget",
    "ProviderFixtureReference",
    "QuoteNormalizationError",
    "QuoteSeries",
    "QuoteSnapshot",
    "ResolvedFixtureIdentity",
    "Selection",
    "ValidatedActiveDixonColesModel",
    "ValueEvaluation",
    "api_football_fixture_identity",
    "api_football_provider_fixture_id",
    "normalize_quote",
    "validate_quotes",
]
