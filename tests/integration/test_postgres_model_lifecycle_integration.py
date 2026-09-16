from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.domain.model_lifecycle import _create_dixon_coles_model_artifact
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.model_lifecycle import ModelActivationConflictError
from h2h.persistence.model_lifecycle import ModelPersistenceConflictError
from h2h.persistence.postgres_model_lifecycle import (
    PostgreSQLActiveDixonColesModelRepository,
    PostgreSQLDixonColesModelVersionRepository,
)
from h2h.quant.dixon_coles_artifact import DixonColesArtifactCodecV1
from h2h.use_cases.model_lifecycle import LoadActiveDixonColesModel
from tests.quant.test_dixon_coles_artifact import TRAINED_AT, trusted_artifact


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MIGRATION_DIR = Path(__file__).parents[2] / "migrations"
SCOPE = DixonColesModelScope("api-football", "api-football", 39, 2024)


@pytest.fixture
def lifecycle():
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        apply_migrations(connection, MIGRATION_DIR)
    versions = PostgreSQLDixonColesModelVersionRepository(database_url=DATABASE_URL)
    active = PostgreSQLActiveDixonColesModelRepository(database_url=DATABASE_URL)
    _, first = trusted_artifact(TRAINED_AT)
    _, second = trusted_artifact(TRAINED_AT + timedelta(seconds=1))
    yield versions, active, first, second
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM dixon_coles_active_models WHERE model_version_id = ANY(%s)",
            ([first.model_version_id, second.model_version_id],),
        )
        cursor.execute(
            "DELETE FROM dixon_coles_model_versions WHERE model_version_id = ANY(%s)",
            ([first.model_version_id, second.model_version_id],),
        )


def test_immutable_version_insert_is_idempotent_and_conflicts_on_changed_bytes(lifecycle):
    versions, _, artifact, _ = lifecycle
    first = versions.add(artifact)
    second = versions.add(artifact)
    assert second == first
    changed = _create_dixon_coles_model_artifact(
        model_version_id=artifact.model_version_id,
        provenance=artifact.provenance,
        python_version=artifact.python_version,
        numpy_version=artifact.numpy_version,
        scipy_version=artifact.scipy_version,
        artifact_sha256=artifact.artifact_sha256,
        artifact_bytes=artifact.artifact_bytes + b"different",
    )
    with pytest.raises(ModelPersistenceConflictError, match="conflicting immutable"):
        versions.add(changed)


def test_concurrent_identical_artifact_persistence_is_idempotent(lifecycle):
    _, _, artifact, _ = lifecycle

    def persist():
        return PostgreSQLDixonColesModelVersionRepository(database_url=DATABASE_URL).add(artifact)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: persist(), range(2)))
    assert results[0] == results[1]
    assert results[0].model_version_id == artifact.model_version_id


def test_concurrent_different_activation_from_same_expected_has_one_winner(lifecycle):
    versions, _, first, second = lifecycle
    versions.add(first)
    versions.add(second)
    now = datetime(2025, 2, 3, tzinfo=UTC)

    def activate(target):
        repository = PostgreSQLActiveDixonColesModelRepository(database_url=DATABASE_URL)
        return repository.compare_and_swap(
            SCOPE,
            target_model_version_id=target,
            expected_current_model_version_id=None,
            activated_at=now,
        )

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(activate, item.model_version_id) for item in (first, second)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except ModelActivationConflictError as exc:
                outcomes.append(exc)
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, ModelActivationConflictError) for item in outcomes) == 1


def test_activation_transition_retry_and_old_version_retention(lifecycle):
    versions, active, first, second = lifecycle
    old = versions.add(first)
    new = versions.add(second)
    activated = active.compare_and_swap(
        SCOPE,
        target_model_version_id=old.model_version_id,
        expected_current_model_version_id=None,
        activated_at=datetime(2025, 2, 3, tzinfo=UTC),
    )
    replaced = active.compare_and_swap(
        SCOPE,
        target_model_version_id=new.model_version_id,
        expected_current_model_version_id=old.model_version_id,
        activated_at=datetime(2025, 2, 4, tzinfo=UTC),
    )
    retry = active.compare_and_swap(
        SCOPE,
        target_model_version_id=new.model_version_id,
        expected_current_model_version_id=old.model_version_id,
        activated_at=datetime(2025, 2, 5, tzinfo=UTC),
    )
    assert activated.generation == 1
    assert replaced.generation == 2
    assert retry == replaced
    assert versions.get(old.model_version_id) == old
    assert DixonColesArtifactCodecV1().decode(old.artifact).model_version_id == old.model_version_id


def test_fresh_repository_instances_load_active_model_after_restart(lifecycle):
    versions, active, artifact, _ = lifecycle
    version = versions.add(artifact)
    active.compare_and_swap(
        SCOPE,
        target_model_version_id=version.model_version_id,
        expected_current_model_version_id=None,
        activated_at=datetime(2025, 2, 3, tzinfo=UTC),
    )
    fresh_versions = PostgreSQLDixonColesModelVersionRepository(database_url=DATABASE_URL)
    fresh_active = PostgreSQLActiveDixonColesModelRepository(database_url=DATABASE_URL)
    loaded = LoadActiveDixonColesModel(fresh_versions, fresh_active).execute(SCOPE)
    assert loaded.model_version_id == version.model_version_id
    assert loaded.scope == SCOPE


def test_complete_migration_chain_contains_model_lifecycle_tables(lifecycle):
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations")
        versions = {row[0] for row in cursor.fetchall()}
        assert "003_dixon_coles_model_lifecycle.sql" in versions
        cursor.execute("SELECT to_regclass('dixon_coles_model_versions')")
        assert cursor.fetchone()[0] == "dixon_coles_model_versions"
        cursor.execute("SELECT to_regclass('dixon_coles_active_models')")
        assert cursor.fetchone()[0] == "dixon_coles_active_models"
