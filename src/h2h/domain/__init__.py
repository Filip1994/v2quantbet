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
from .pick_decision import (
    BankrollRiskSnapshot,
    DecisionOutcome,
    EligibilityRejectionCode,
    FixedStakeDecision,
    PickDecision,
    PickLifecycleState,
    RegisteredPick,
    RegistrationResult,
    RejectionStage,
    RiskRejectionCode,
)
from .registration_policy import RegistrationPolicyConfig
from .pick_monitoring import (
    ODDS_LIFECYCLE_V1,
    ClosingFinalization,
    ClosingOutcome,
    MonitoringRecord,
    MonitoringState,
    MonitoringTransitionType,
    OddsCheckpoint,
    OddsLifecyclePolicy,
    PickOddsLifecycle,
    QuoteFreshness,
)
from .fixture_result import (
    RESULT_NORMALIZER_VERSION,
    ApiFootballSettlementResultNormalizer,
    FixtureResultObservation,
    ResultClassification,
)
from .settlement import (
    CLV_METHOD_VERSION,
    MONEY_ROUNDING_VERSION,
    SETTLEMENT_RULE_VERSION,
    ClvAvailability,
    ResultSettlementPolicy,
    SettlementEventKind,
    SettlementOutcome,
    realized_clv_ppm,
    settle_market,
    settlement_amounts,
)

__all__ = [
    "CLV_METHOD_VERSION",
    "MONEY_ROUNDING_VERSION",
    "ODDS_LIFECYCLE_V1",
    "PROPORTIONAL_TWO_WAY_V1",
    "RESULT_NORMALIZER_VERSION",
    "SETTLEMENT_RULE_VERSION",
    "ActiveDixonColesModel",
    "ApiFootballSettlementResultNormalizer",
    "BankrollRiskSnapshot",
    "CanonicalQuote",
    "ClosingFinalization",
    "ClosingOutcome",
    "ClvAvailability",
    "DecisionOutcome",
    "DixonColesModelArtifact",
    "DixonColesModelScope",
    "DixonColesModelVersion",
    "DixonColesTrainingConfig",
    "DixonColesTrainingProvenance",
    "EligibilityRejectionCode",
    "FixedStakeDecision",
    "Fixture",
    "FixtureIdentityRecord",
    "FixtureObservation",
    "FixturePrediction",
    "FixtureResultObservation",
    "LoadedDixonColesModelVersion",
    "Market",
    "MarketSnapshot",
    "MonitoringRecord",
    "MonitoringState",
    "MonitoringTransitionType",
    "OddsCheckpoint",
    "OddsLifecyclePolicy",
    "PersistedFixture",
    "PersistedFixturePrediction",
    "PersistedMarketObservation",
    "PersistedQuoteObservation",
    "PickDecision",
    "PickLifecycleState",
    "PickOddsLifecycle",
    "PickRegistration",
    "PickStatus",
    "PredictionTarget",
    "ProviderFixtureReference",
    "QuoteFreshness",
    "QuoteNormalizationError",
    "QuoteSeries",
    "QuoteSnapshot",
    "RegisteredPick",
    "RegistrationPolicyConfig",
    "RegistrationResult",
    "RejectionStage",
    "ResolvedFixtureIdentity",
    "ResultClassification",
    "ResultSettlementPolicy",
    "RiskRejectionCode",
    "Selection",
    "SettlementEventKind",
    "SettlementOutcome",
    "ValidatedActiveDixonColesModel",
    "ValueEvaluation",
    "api_football_fixture_identity",
    "api_football_provider_fixture_id",
    "normalize_quote",
    "realized_clv_ppm",
    "settle_market",
    "settlement_amounts",
    "validate_quotes",
]
