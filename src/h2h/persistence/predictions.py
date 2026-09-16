"""Persistence contract for immutable production predictions."""

from typing import Protocol

from h2h.domain.prediction_record import PersistedFixturePrediction


class PredictionPersistenceConflictError(ValueError):
    """A prediction identity or natural execution key conflicts."""


class FixturePredictionRepository(Protocol):
    def add(self, prediction: PersistedFixturePrediction) -> PersistedFixturePrediction: ...

    def get(self, prediction_id: str) -> PersistedFixturePrediction | None: ...
