"""Application use cases coordinating provider-neutral domain boundaries."""

from .fixture_prediction import (
    DixonColesFixturePredictor,
    PredictionFixtureMismatchError,
    TeamIdNamespaceMismatchError,
    evaluate_prediction_quote,
)
from .api_football_training import (
    ApiFootballHistoricalResults,
    ApiFootballTrainingDataset,
    ApiFootballTrainingScope,
    fit_api_football_dixon_coles,
    normalize_api_football_historical_response,
)
from .quote_history import QuoteHistoryIngestionService
from .durable_fixture_discovery import DurableFixtureDiscovery
from .value_evaluation import EvaluatePersistedPredictionQuote, EvaluationFixtureMismatchError
from .quotes import QuoteIngestionService
from .register_pick import BootstrapBankroll, RegisterEligiblePick
from .pick_monitoring import (
    FinalizePickClosingOdds,
    ReadPickOddsLifecycle,
    ReconcileRegisteredPickMonitoring,
    RefreshRegisteredPickOdds,
    StartRegisteredPickMonitoring,
)
from .result_settlement import ApiFootballResultSource, ReconcileFixtureResults, ResultCycle


def __getattr__(name: str):
    """Load the production predictor lazily to avoid the artifact/training import cycle."""
    if name == "ProduceFixturePrediction":
        from .production_prediction import ProduceFixturePrediction

        return ProduceFixturePrediction
    raise AttributeError(name)

__all__ = [
    "ApiFootballHistoricalResults",
    "ApiFootballResultSource",
    "ApiFootballTrainingDataset",
    "ApiFootballTrainingScope",
    "BootstrapBankroll",
    "DixonColesFixturePredictor",
    "DurableFixtureDiscovery",
    "EvaluatePersistedPredictionQuote",
    "EvaluationFixtureMismatchError",
    "FinalizePickClosingOdds",
    "PredictionFixtureMismatchError",
    "ProduceFixturePrediction",
    "QuoteHistoryIngestionService",
    "QuoteIngestionService",
    "ReadPickOddsLifecycle",
    "ReconcileFixtureResults",
    "ReconcileRegisteredPickMonitoring",
    "RefreshRegisteredPickOdds",
    "RegisterEligiblePick",
    "ResultCycle",
    "StartRegisteredPickMonitoring",
    "TeamIdNamespaceMismatchError",
    "evaluate_prediction_quote",
    "fit_api_football_dixon_coles",
    "normalize_api_football_historical_response",
]
