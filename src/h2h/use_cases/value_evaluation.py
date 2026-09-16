"""Evaluate one persisted prediction against one exact persisted market observation."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from h2h.domain.value_evaluation import PROPORTIONAL_TWO_WAY_V1, ValueEvaluation
from h2h.persistence.predictions import FixturePredictionRepository
from h2h.persistence.quote_history import QuoteHistoryRepository
from h2h.persistence.value_evaluations import ValueEvaluationRepository
from h2h.quant.market_probability import model_probability_for_selection


class EvaluationFixtureMismatchError(ValueError):
    """The prediction and persisted market observation target different fixtures."""


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _evaluation_id(payload: dict[str, str]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "value-evaluation-v1:" + sha256(encoded).hexdigest()


class EvaluatePersistedPredictionQuote:
    def __init__(
        self,
        predictions: FixturePredictionRepository,
        quote_history: QuoteHistoryRepository,
        evaluations: ValueEvaluationRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._predictions = predictions
        self._quote_history = quote_history
        self._evaluations = evaluations
        self._clock = clock

    def execute(self, prediction_id: str, selected_snapshot_id: str) -> ValueEvaluation:
        prediction = self._predictions.get(prediction_id)
        if prediction is None:
            raise LookupError(f"prediction {prediction_id!r} does not exist")
        market = self._quote_history.complete_market_observation_for_snapshot(selected_snapshot_id)
        if market is None:
            raise LookupError(f"quote snapshot {selected_snapshot_id!r} does not exist")
        selected, companion = market.selected(selected_snapshot_id)
        if prediction.fixture_id != selected.fixture_id:
            raise EvaluationFixtureMismatchError(
                "prediction and market observation must share canonical fixture identity"
            )
        model_probability = model_probability_for_selection(
            prediction.probabilities,
            market=selected.market,
            selection=selected.selection,
        )
        selected_raw = 1.0 / selected.odd
        companion_raw = 1.0 / companion.odd
        overround = selected_raw + companion_raw
        selected_devig = selected_raw / overround
        evaluated_at = _now(self._clock)
        semantic = {
            "companion_snapshot_id": companion.snapshot_id,
            "devig_method_version": PROPORTIONAL_TWO_WAY_V1,
            "prediction_id": prediction.prediction_id,
            "selected_snapshot_id": selected.snapshot_id,
        }
        evaluation = ValueEvaluation(
            evaluation_id=_evaluation_id(semantic),
            fixture_id=prediction.fixture_id,
            prediction_id=prediction.prediction_id,
            model_version_id=prediction.model_version_id,
            selected_series_id=selected.series_id,
            companion_series_id=companion.series_id,
            selected_snapshot_id=selected.snapshot_id,
            companion_snapshot_id=companion.snapshot_id,
            bookmaker_id=selected.bookmaker_id,
            bookmaker_key=selected.bookmaker_key,
            market=selected.market,
            selected_selection=selected.selection,
            companion_selection=companion.selection,
            quote_observed_at=selected.observed_at,
            source=selected.source,
            selected_captured_at=selected.captured_at,
            companion_captured_at=companion.captured_at,
            selected_odd=selected.odd,
            companion_odd=companion.odd,
            selected_raw_implied_probability=selected_raw,
            companion_raw_implied_probability=companion_raw,
            overround=overround,
            devig_method_version=PROPORTIONAL_TWO_WAY_V1,
            selected_devig_probability=selected_devig,
            model_probability=model_probability,
            edge=model_probability - selected_devig,
            expected_value=model_probability * selected.odd - 1.0,
            evaluated_at=evaluated_at,
            persisted_at=evaluated_at,
        )
        return self._evaluations.add(evaluation)
