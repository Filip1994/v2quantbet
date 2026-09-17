"""PostgreSQL persistence for immutable Dixon-Coles model versions."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from h2h.domain.model_lifecycle import (
    ActiveDixonColesModel,
    DixonColesModelArtifact,
    DixonColesModelScope,
    DixonColesModelVersion,
    _create_dixon_coles_model_artifact,
    _is_trusted_dixon_coles_model_artifact,
)
from h2h.persistence.model_lifecycle import (
    ModelActivationConflictError,
    ModelPersistenceConflictError,
)


ConnectionFactory = Callable[[], Any]

_VERSION_COLUMNS = (
    "model_version_id, provider, team_id_namespace, league_id, season, "
    "training_start_at, training_end_at, reference_time, xi, ridge, min_matches, "
    "accepted_match_count, fitted_match_count, earliest_match_at, latest_match_at, "
    "dataset_sha256, training_input_fingerprint, trained_at, persisted_at, "
    "artifact_schema_version, training_dataset_schema_version, "
    "model_implementation_version, trainer_code_version, python_version, "
    "numpy_version, scipy_version, artifact_sha256, artifact_bytes"
)


class _PostgreSQLConnections:
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


class PostgreSQLDixonColesModelVersionRepository(_PostgreSQLConnections):
    def add(self, artifact: DixonColesModelArtifact) -> DixonColesModelVersion:
        if not _is_trusted_dixon_coles_model_artifact(artifact):
            raise TypeError("artifact must come from trusted model lifecycle construction")
        values = self._artifact_values(artifact)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dixon_coles_model_versions ("
                + _VERSION_COLUMNS.replace(", persisted_at", "")
                + ") VALUES ("
                + ", ".join(["%s"] * len(values))
                + ") ON CONFLICT DO NOTHING",
                values,
            )
            cursor.execute(
                f"SELECT {_VERSION_COLUMNS} FROM dixon_coles_model_versions "
                "WHERE model_version_id = %s",
                (artifact.model_version_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ModelPersistenceConflictError("persisted model version could not be resolved")
            stored = self._row_to_version(row)
            if stored.artifact != artifact:
                raise ModelPersistenceConflictError(
                    f"conflicting immutable model version {artifact.model_version_id!r}"
                )
            return stored

    def get(self, model_version_id: str) -> DixonColesModelVersion | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_VERSION_COLUMNS} FROM dixon_coles_model_versions "
                "WHERE model_version_id = %s",
                (model_version_id,),
            )
            row = cursor.fetchone()
            return None if row is None else self._row_to_version(row)

    def list_for_scope(
        self, scope: DixonColesModelScope
    ) -> tuple[DixonColesModelVersion, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_VERSION_COLUMNS} FROM dixon_coles_model_versions "
                "WHERE provider = %s AND team_id_namespace = %s "
                "AND league_id = %s AND season = %s "
                "ORDER BY trained_at, model_version_id",
                _scope_values(scope),
            )
            return tuple(self._row_to_version(row) for row in cursor.fetchall())

    @staticmethod
    def _artifact_values(artifact: DixonColesModelArtifact) -> tuple[object, ...]:
        p = artifact.provenance
        target = artifact.scope
        return (
            artifact.model_version_id,
            target.provider,
            target.team_id_namespace,
            target.league_id,
            target.season,
            p.training_start_at,
            p.training_end_at,
            p.reference_time,
            p.xi,
            p.ridge,
            p.min_matches,
            p.accepted_match_count,
            p.fitted_match_count,
            p.earliest_match_at,
            p.latest_match_at,
            p.dataset_sha256,
            p.training_input_fingerprint,
            p.trained_at,
            p.artifact_schema_version,
            p.training_dataset_schema_version,
            p.model_implementation_version,
            p.trainer_code_version,
            artifact.python_version,
            artifact.numpy_version,
            artifact.scipy_version,
            artifact.artifact_sha256,
            artifact.artifact_bytes,
        )

    @staticmethod
    def _row_to_version(row: tuple[Any, ...]) -> DixonColesModelVersion:
        # Non-searchable provenance is protected by the artifact digest. Decode it
        # once here so the returned immutable version carries the complete values.
        from h2h.quant.dixon_coles_artifact import (
            _provenance_from_artifact_bytes,
            _target_scope_from_artifact_bytes,
        )

        complete = _provenance_from_artifact_bytes(bytes(row[27]))
        target_scope = _target_scope_from_artifact_bytes(bytes(row[27]))
        if tuple(row[1:5]) != _scope_values(target_scope):
            raise ModelPersistenceConflictError(
                "stored model scope contradicts artifact target scope"
            )
        expected = (
            complete.training_start_at,
            complete.training_end_at,
            complete.reference_time,
            complete.xi,
            complete.ridge,
            complete.min_matches,
            complete.accepted_match_count,
            complete.fitted_match_count,
            complete.earliest_match_at,
            complete.latest_match_at,
            complete.dataset_sha256,
            complete.training_input_fingerprint,
            complete.trained_at,
            complete.artifact_schema_version,
            complete.training_dataset_schema_version,
            complete.model_implementation_version,
            complete.trainer_code_version,
        )
        actual = (*row[5:18], *row[19:23])
        if actual != expected:
            raise ModelPersistenceConflictError(
                "stored model metadata contradicts artifact provenance"
            )
        artifact = _create_dixon_coles_model_artifact(
            model_version_id=row[0],
            provenance=complete,
            python_version=row[23],
            numpy_version=row[24],
            scipy_version=row[25],
            artifact_sha256=row[26],
            artifact_bytes=bytes(row[27]),
            target_scope=target_scope,
        )
        return DixonColesModelVersion(artifact=artifact, persisted_at=row[18])


class PostgreSQLActiveDixonColesModelRepository(_PostgreSQLConnections):
    def get_active(self, scope: DixonColesModelScope) -> ActiveDixonColesModel | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT provider, team_id_namespace, league_id, season, "
                "model_version_id, activated_at, generation "
                "FROM dixon_coles_active_models WHERE provider = %s "
                "AND team_id_namespace = %s AND league_id = %s AND season = %s",
                _scope_values(scope),
            )
            row = cursor.fetchone()
            return None if row is None else _row_to_active(row)

    def compare_and_swap(
        self,
        scope: DixonColesModelScope,
        *,
        target_model_version_id: str,
        expected_current_model_version_id: str | None,
        activated_at: datetime,
    ) -> ActiveDixonColesModel:
        with self.connect() as connection, connection.cursor() as cursor:
            if expected_current_model_version_id is None:
                cursor.execute(
                    "INSERT INTO dixon_coles_active_models "
                    "(provider, team_id_namespace, league_id, season, model_version_id, "
                    "activated_at, generation) VALUES (%s, %s, %s, %s, %s, %s, 1) "
                    "ON CONFLICT (provider, team_id_namespace, league_id, season) DO NOTHING "
                    "RETURNING provider, team_id_namespace, league_id, season, "
                    "model_version_id, activated_at, generation",
                    (*_scope_values(scope), target_model_version_id, activated_at),
                )
            else:
                cursor.execute(
                    "UPDATE dixon_coles_active_models SET model_version_id = %s, "
                    "activated_at = %s, generation = generation + 1 "
                    "WHERE provider = %s AND team_id_namespace = %s "
                    "AND league_id = %s AND season = %s AND model_version_id = %s "
                    "AND model_version_id <> %s "
                    "RETURNING provider, team_id_namespace, league_id, season, "
                    "model_version_id, activated_at, generation",
                    (
                        target_model_version_id,
                        activated_at,
                        *_scope_values(scope),
                        expected_current_model_version_id,
                        target_model_version_id,
                    ),
                )
            changed = cursor.fetchone()
            if changed is not None:
                return _row_to_active(changed)
            cursor.execute(
                "SELECT provider, team_id_namespace, league_id, season, model_version_id, "
                "activated_at, generation FROM dixon_coles_active_models "
                "WHERE provider = %s AND team_id_namespace = %s "
                "AND league_id = %s AND season = %s",
                _scope_values(scope),
            )
            current = cursor.fetchone()
            if current is not None and current[4] == target_model_version_id:
                return _row_to_active(current)
            actual = None if current is None else current[4]
            raise ModelActivationConflictError(
                f"active model changed: expected {expected_current_model_version_id!r}, "
                f"found {actual!r}"
            )

    def list_active(self) -> tuple[ActiveDixonColesModel, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT provider, team_id_namespace, league_id, season, model_version_id, "
                "activated_at, generation FROM dixon_coles_active_models "
                "ORDER BY provider, team_id_namespace, league_id, season"
            )
            return tuple(_row_to_active(row) for row in cursor.fetchall())


def _scope_values(scope: DixonColesModelScope) -> tuple[object, ...]:
    return scope.provider, scope.team_id_namespace, scope.league_id, scope.season


def _row_to_active(row: tuple[Any, ...]) -> ActiveDixonColesModel:
    return ActiveDixonColesModel(
        scope=DixonColesModelScope(row[0], row[1], row[2], row[3]),
        model_version_id=row[4],
        activated_at=row[5],
        generation=row[6],
    )
