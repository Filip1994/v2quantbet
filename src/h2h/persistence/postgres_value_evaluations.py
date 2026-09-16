"""PostgreSQL persistence for immutable value evaluations."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from h2h.domain.odds import Market, Selection
from h2h.domain.value_evaluation import ValueEvaluation
from h2h.persistence.value_evaluations import ValueEvaluationPersistenceConflictError


ConnectionFactory = Callable[[], Any]
_COLUMNS = (
    "evaluation_id, fixture_id, prediction_id, model_version_id, selected_series_id, "
    "companion_series_id, selected_snapshot_id, companion_snapshot_id, bookmaker_id, "
    "bookmaker_key, market, selected_selection, companion_selection, quote_observed_at, "
    "source, selected_captured_at, companion_captured_at, selected_odd, companion_odd, "
    "selected_raw_implied_probability, companion_raw_implied_probability, overround, "
    "devig_method_version, selected_devig_probability, model_probability, edge, "
    "expected_value, evaluated_at, persisted_at"
)


class PostgreSQLValueEvaluationRepository:
    def __init__(
        self, database_url: str | None = None, *, connect: ConnectionFactory | None = None
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect

    def connect(self) -> Any:
        if self._connect_factory is not None:
            return self._connect_factory()
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg[binary]") from exc
        return psycopg.connect(self._database_url)

    def add(self, evaluation: ValueEvaluation) -> ValueEvaluation:
        if not isinstance(evaluation, ValueEvaluation):
            raise TypeError("evaluation must be a ValueEvaluation")
        evaluation.validate_arithmetic()
        values = self._values(evaluation)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO value_evaluations ({_COLUMNS}) VALUES "
                f"({', '.join(['%s'] * len(values))}) ON CONFLICT DO NOTHING",
                values,
            )
            cursor.execute(
                f"SELECT {_COLUMNS} FROM value_evaluations WHERE evaluation_id = %s",
                (evaluation.evaluation_id,),
            )
            by_id = cursor.fetchone()
            cursor.execute(
                f"SELECT {_COLUMNS} FROM value_evaluations WHERE prediction_id = %s "
                "AND selected_snapshot_id = %s AND companion_snapshot_id = %s "
                "AND devig_method_version = %s",
                (
                    evaluation.prediction_id,
                    evaluation.selected_snapshot_id,
                    evaluation.companion_snapshot_id,
                    evaluation.devig_method_version,
                ),
            )
            by_natural = cursor.fetchone()
            if by_id is None or by_natural is None or by_id != by_natural:
                raise ValueEvaluationPersistenceConflictError("evaluation identity conflicts")
            stored = self._row(by_id)
            if self._semantic(stored) != self._semantic(evaluation):
                raise ValueEvaluationPersistenceConflictError("conflicting immutable evaluation")
            stored.validate_arithmetic()
            return stored

    def get(self, evaluation_id: str) -> ValueEvaluation | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_COLUMNS} FROM value_evaluations WHERE evaluation_id = %s",
                (evaluation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            value = self._row(row)
            value.validate_arithmetic()
            return value

    @staticmethod
    def _values(value: ValueEvaluation) -> tuple[object, ...]:
        return (
            value.evaluation_id,
            value.fixture_id,
            value.prediction_id,
            value.model_version_id,
            value.selected_series_id,
            value.companion_series_id,
            value.selected_snapshot_id,
            value.companion_snapshot_id,
            value.bookmaker_id,
            value.bookmaker_key,
            value.market.value,
            value.selected_selection.value,
            value.companion_selection.value,
            value.quote_observed_at,
            value.source,
            value.selected_captured_at,
            value.companion_captured_at,
            value.selected_odd,
            value.companion_odd,
            value.selected_raw_implied_probability,
            value.companion_raw_implied_probability,
            value.overround,
            value.devig_method_version,
            value.selected_devig_probability,
            value.model_probability,
            value.edge,
            value.expected_value,
            value.evaluated_at,
            value.persisted_at,
        )

    @staticmethod
    def _row(row: tuple[Any, ...]) -> ValueEvaluation:
        values = list(row)
        values[10] = Market(values[10])
        values[11] = Selection(values[11])
        values[12] = Selection(values[12])
        return ValueEvaluation(*values)

    @classmethod
    def _semantic(cls, value: ValueEvaluation) -> tuple[object, ...]:
        return cls._values(value)[:-2]
