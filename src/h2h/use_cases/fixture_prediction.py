"""Identity-safe fixture prediction and quote valuation boundaries."""

from h2h.domain.fixture import Fixture
from h2h.domain.odds import CanonicalQuote
from h2h.domain.prediction import (
    FixturePrediction,
    _fixture_prediction_from_execution,
    _is_fixture_prediction,
    _prediction_target_from_fixture,
)
from h2h.domain.value_pick import ValuePick, evaluate_value
from h2h.quant.dixon_coles import DixonColesModel
from h2h.quant.market_probability import model_probability_for_selection


class TeamIdNamespaceMismatchError(ValueError):
    """The fitted model and prediction target use different team-ID namespaces."""


class PredictionFixtureMismatchError(ValueError):
    """A quote does not belong to the fixture targeted by a prediction."""


class DixonColesFixturePredictor:
    """Run Dixon–Coles only for an authoritative, namespace-compatible fixture."""

    def __init__(self, model: DixonColesModel) -> None:
        if not isinstance(model, DixonColesModel):
            raise TypeError("model must be a DixonColesModel")
        self._model = model

    def predict(
        self,
        fixture: Fixture,
        *,
        max_goals: int = 10,
    ) -> FixturePrediction:
        """Predict the exact ordered team target derived from ``fixture``."""
        target = _prediction_target_from_fixture(fixture)
        if self._model.team_id_namespace != target.team_id_namespace:
            raise TeamIdNamespaceMismatchError(
                "model team-ID namespace does not match prediction target namespace"
            )
        probabilities = self._model.market_probabilities(
            target.home_team_id,
            target.away_team_id,
            max_goals=max_goals,
        )
        return _fixture_prediction_from_execution(
            target=target,
            probabilities=probabilities,
        )


def evaluate_prediction_quote(
    prediction: FixturePrediction,
    quote: CanonicalQuote,
) -> ValuePick:
    """Value a quote only when it belongs to the prediction's canonical fixture."""
    if not _is_fixture_prediction(prediction):
        raise TypeError("prediction must be produced by DixonColesFixturePredictor")
    if not isinstance(quote, CanonicalQuote):
        raise TypeError("quote must be a CanonicalQuote")
    if prediction.target.fixture_id != quote.fixture_id:
        raise PredictionFixtureMismatchError(
            "prediction and quote must belong to the same canonical fixture"
        )
    probability = model_probability_for_selection(
        prediction.probabilities,
        market=quote.market,
        selection=quote.selection,
    )
    return evaluate_value(quote, probability)
