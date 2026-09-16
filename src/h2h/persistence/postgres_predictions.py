"""PostgreSQL persistence for immutable production predictions."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from h2h.domain.prediction_record import PersistedFixturePrediction
from h2h.persistence.predictions import PredictionPersistenceConflictError


ConnectionFactory = Callable[[], Any]
_COLUMNS = (
    "prediction_id, fixture_id, fixture_observation_id, model_version_id, "
    "active_generation, model_activated_at, provider, team_id_namespace, league_id, "
    "season, provider_home_team_id, provider_away_team_id, prediction_method_version, "
    "max_goals, over_2_5_probability, under_2_5_probability, btts_yes_probability, "
    "predicted_at, persisted_at"
)


class PostgreSQLFixturePredictionRepository:
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

    def add(self, prediction: PersistedFixturePrediction) -> PersistedFixturePrediction:
        if not isinstance(prediction, PersistedFixturePrediction):
            raise TypeError("prediction must be a PersistedFixturePrediction")
        values = self._values(prediction)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO fixture_predictions ({_COLUMNS}) VALUES "
                f"({', '.join(['%s'] * len(values))}) ON CONFLICT DO NOTHING",
                values,
            )
            cursor.execute(
                f"SELECT {_COLUMNS} FROM fixture_predictions WHERE prediction_id = %s",
                (prediction.prediction_id,),
            )
            by_id = cursor.fetchone()
            cursor.execute(
                f"SELECT {_COLUMNS} FROM fixture_predictions WHERE fixture_observation_id = %s "
                "AND model_version_id = %s AND active_generation = %s "
                "AND prediction_method_version = %s AND max_goals = %s",
                (
                    prediction.fixture_observation_id,
                    prediction.model_version_id,
                    prediction.active_generation,
                    prediction.prediction_method_version,
                    prediction.max_goals,
                ),
            )
            by_natural = cursor.fetchone()
            if by_id is None or by_natural is None or by_id != by_natural:
                raise PredictionPersistenceConflictError("prediction identity conflicts")
            stored = self._row(by_id)
            if self._semantic(stored) != self._semantic(prediction):
                raise PredictionPersistenceConflictError("conflicting immutable prediction")
            return stored

    def get(self, prediction_id: str) -> PersistedFixturePrediction | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_COLUMNS} FROM fixture_predictions WHERE prediction_id = %s",
                (prediction_id,),
            )
            row = cursor.fetchone()
            return None if row is None else self._row(row)

    @staticmethod
    def _values(value: PersistedFixturePrediction) -> tuple[object, ...]:
        return (
            value.prediction_id,
            value.fixture_id,
            value.fixture_observation_id,
            value.model_version_id,
            value.active_generation,
            value.model_activated_at,
            value.provider,
            value.team_id_namespace,
            value.league_id,
            value.season,
            value.provider_home_team_id,
            value.provider_away_team_id,
            value.prediction_method_version,
            value.max_goals,
            value.over_2_5_probability,
            value.under_2_5_probability,
            value.btts_yes_probability,
            value.predicted_at,
            value.persisted_at,
        )

    @staticmethod
    def _row(row: tuple[Any, ...]) -> PersistedFixturePrediction:
        return PersistedFixturePrediction(*row)

    @classmethod
    def _semantic(cls, value: PersistedFixturePrediction) -> tuple[object, ...]:
        return cls._values(value)[:-2]
