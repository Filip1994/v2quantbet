"""Persistence contract for immutable value evaluations."""

from typing import Protocol

from h2h.domain.value_evaluation import ValueEvaluation


class ValueEvaluationPersistenceConflictError(ValueError):
    """An evaluation identity or semantic key conflicts."""


class ValueEvaluationRepository(Protocol):
    def add(self, evaluation: ValueEvaluation) -> ValueEvaluation: ...

    def get(self, evaluation_id: str) -> ValueEvaluation | None: ...
