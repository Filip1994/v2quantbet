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
from .quotes import QuoteIngestionService

__all__ = [
    "ApiFootballHistoricalResults",
    "ApiFootballTrainingDataset",
    "ApiFootballTrainingScope",
    "DixonColesFixturePredictor",
    "PredictionFixtureMismatchError",
    "QuoteHistoryIngestionService",
    "QuoteIngestionService",
    "TeamIdNamespaceMismatchError",
    "evaluate_prediction_quote",
    "fit_api_football_dixon_coles",
    "normalize_api_football_historical_response",
]
