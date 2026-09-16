from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.persistence.model_lifecycle import ModelActivationConflictError
from h2h.persistence.model_lifecycle import ModelPersistenceConflictError
from h2h.persistence.postgres_model_lifecycle import (
    PostgreSQLActiveDixonColesModelRepository,
    PostgreSQLDixonColesModelVersionRepository,
)
from tests.quant.test_dixon_coles_artifact import TRAINED_AT, trusted_artifact


NOW = datetime(2025, 2, 3, tzinfo=UTC)
SCOPE = DixonColesModelScope("api-football", "api-football", 39, 2024)


def row_for(artifact):
    p = artifact.provenance
    return (
        artifact.model_version_id,
        p.provider,
        p.team_id_namespace,
        p.league_id,
        p.season,
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
        NOW,
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


def connection_with_cursor(cursor):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection


def test_version_add_uses_immutable_insert_and_reconstructs_complete_version() -> None:
    _, artifact = trusted_artifact()
    cursor = MagicMock()
    cursor.fetchone.return_value = row_for(artifact)
    repository = PostgreSQLDixonColesModelVersionRepository(
        connect=lambda: connection_with_cursor(cursor)
    )
    version = repository.add(artifact)
    assert version.artifact == artifact
    assert version.persisted_at == NOW
    insert_sql = cursor.execute.call_args_list[0].args[0]
    assert "ON CONFLICT DO NOTHING" in insert_sql
    assert "persisted_at" not in insert_sql.split(") VALUES", maxsplit=1)[0]


def test_version_add_rejects_existing_row_with_other_immutable_content() -> None:
    _, artifact = trusted_artifact()
    _, other = trusted_artifact(TRAINED_AT + timedelta(seconds=1))
    cursor = MagicMock()
    cursor.fetchone.return_value = row_for(other)
    repository = PostgreSQLDixonColesModelVersionRepository(
        connect=lambda: connection_with_cursor(cursor)
    )
    with pytest.raises(ModelPersistenceConflictError, match="conflicting immutable"):
        repository.add(artifact)


def test_cas_insert_and_same_target_retry_do_not_increment_generation() -> None:
    _, artifact = trusted_artifact()
    active_row = (
        SCOPE.provider,
        SCOPE.team_id_namespace,
        SCOPE.league_id,
        SCOPE.season,
        artifact.model_version_id,
        NOW,
        1,
    )
    cursor = MagicMock()
    cursor.fetchone.side_effect = [active_row]
    repository = PostgreSQLActiveDixonColesModelRepository(
        connect=lambda: connection_with_cursor(cursor)
    )
    created = repository.compare_and_swap(
        SCOPE,
        target_model_version_id=artifact.model_version_id,
        expected_current_model_version_id=None,
        activated_at=NOW,
    )
    assert created.generation == 1
    assert "ON CONFLICT" in cursor.execute.call_args_list[0].args[0]

    retry_cursor = MagicMock()
    retry_cursor.fetchone.side_effect = [None, active_row]
    retry = PostgreSQLActiveDixonColesModelRepository(
        connect=lambda: connection_with_cursor(retry_cursor)
    ).compare_and_swap(
        SCOPE,
        target_model_version_id=artifact.model_version_id,
        expected_current_model_version_id="previous",
        activated_at=NOW + timedelta(seconds=1),
    )
    assert retry.generation == 1
    assert retry.activated_at == NOW


def test_cas_stale_expected_version_raises_conflict() -> None:
    _, artifact = trusted_artifact()
    active_row = (
        SCOPE.provider,
        SCOPE.team_id_namespace,
        SCOPE.league_id,
        SCOPE.season,
        "different-version",
        NOW,
        2,
    )
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, active_row]
    repository = PostgreSQLActiveDixonColesModelRepository(
        connect=lambda: connection_with_cursor(cursor)
    )
    with pytest.raises(ModelActivationConflictError, match="active model changed"):
        repository.compare_and_swap(
            SCOPE,
            target_model_version_id=artifact.model_version_id,
            expected_current_model_version_id="expected-version",
            activated_at=NOW,
        )
