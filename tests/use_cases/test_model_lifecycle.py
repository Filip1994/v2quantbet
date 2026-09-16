from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from h2h.application import build_trusted_api_football_historical_results
from h2h.config import ApplicationSettings
from h2h.domain.model_lifecycle import ActiveDixonColesModel, DixonColesModelScope
from h2h.domain.model_lifecycle import DixonColesModelVersion, DixonColesTrainingConfig
from h2h.odds.http import UrllibJsonTransport
from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.persistence.model_lifecycle import ModelActivationConflictError
from h2h.quant.dixon_coles_artifact import _create_dixon_coles_model_artifact
from h2h.use_cases.api_football_training import ApiFootballTrainingScope
from h2h.use_cases.model_lifecycle import (
    ActivateDixonColesModel,
    InsufficientTrainingDataError,
    LoadActiveDixonColesModel,
    TrainApiFootballDixonColesModel,
)


START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 2, 1, tzinfo=UTC)
NOW = datetime(2025, 2, 2, tzinfo=UTC)
SCOPE = DixonColesModelScope("api-football", "api-football", 39, 2024)


def provider_payload(count=24):
    response = []
    teams = (1, 2, 3, 4)
    for index in range(count):
        home = teams[index % 4]
        away = teams[(index + 1 + index // 4) % 4]
        if home == away:
            away = teams[(teams.index(away) + 1) % 4]
        home_goals, away_goals = index % 3, (index + 1) % 2
        response.append(
            {
                "fixture": {
                    "id": 1000 + index,
                    "date": (START + timedelta(days=index)).isoformat(),
                    "status": {"short": "FT"},
                },
                "league": {"id": 39, "season": 2024},
                "teams": {"home": {"id": home}, "away": {"id": away}},
                "goals": {"home": home_goals, "away": away_goals},
                "score": {
                    "fulltime": {"home": home_goals, "away": away_goals},
                    "extratime": {"home": None, "away": None},
                    "penalty": {"home": None, "away": None},
                },
            }
        )
    return {
        "errors": [],
        "results": len(response),
        "paging": {"current": 1, "total": 1},
        "response": response,
    }


class MemoryVersions:
    def __init__(self):
        self.items = {}

    def add(self, artifact):
        existing = self.items.get(artifact.model_version_id)
        if existing is not None:
            return existing
        version = DixonColesModelVersion(artifact, NOW)
        self.items[artifact.model_version_id] = version
        return version

    def get(self, model_version_id):
        return self.items.get(model_version_id)

    def list_for_scope(self, scope):
        return tuple(item for item in self.items.values() if item.scope == scope)


class MemoryActive:
    def __init__(self):
        self.items = {}

    def get_active(self, scope):
        return self.items.get(scope)

    def compare_and_swap(
        self,
        scope,
        *,
        target_model_version_id,
        expected_current_model_version_id,
        activated_at,
    ):
        current = self.items.get(scope)
        if current is not None and current.model_version_id == target_model_version_id:
            return current
        actual = None if current is None else current.model_version_id
        if actual != expected_current_model_version_id:
            raise ModelActivationConflictError("stale expected model")
        active = ActiveDixonColesModel(
            scope,
            target_model_version_id,
            activated_at,
            1 if current is None else current.generation + 1,
        )
        self.items[scope] = active
        return active

    def list_active(self):
        return tuple(self.items.values())


class FailingVersions(MemoryVersions):
    def add(self, artifact):
        del artifact
        raise RuntimeError("database unavailable")


def historical_results():
    settings = ApplicationSettings(database_path="unused.sqlite3", api_football_key="secret")
    return build_trusted_api_football_historical_results(settings)


def config(**changes):
    values = {
        "reference_time": END,
        "xi": 0.001,
        "ridge": 0.01,
        "min_matches": 20,
        "trainer_code_version": "test-build",
    }
    values.update(changes)
    return DixonColesTrainingConfig(**values)


def _trusted_artifact_for_test():
    versions = MemoryVersions()
    trainer = TrainApiFootballDixonColesModel(
        historical_results(), versions, clock=lambda: NOW
    )
    with patch.object(UrllibJsonTransport, "get_json", return_value=provider_payload()):
        version = trainer.execute(ApiFootballTrainingScope(39, 2024, START, END), config())
    return version, version.artifact


def test_training_persists_inactive_version_and_loader_requires_activation() -> None:
    versions, active = MemoryVersions(), MemoryActive()
    trainer = TrainApiFootballDixonColesModel(
        historical_results(), versions, clock=lambda: NOW
    )
    with patch.object(UrllibJsonTransport, "get_json", return_value=provider_payload()):
        version = trainer.execute(ApiFootballTrainingScope(39, 2024, START, END), config())
    assert version.model_version_id in versions.items
    assert active.get_active(SCOPE) is None
    with pytest.raises(ActiveModelUnavailableError, match="no active"):
        LoadActiveDixonColesModel(versions, active).execute(SCOPE)


@pytest.mark.parametrize("count", [0, 10])
def test_empty_and_insufficient_training_data_create_no_version(count) -> None:
    versions = MemoryVersions()
    trainer = TrainApiFootballDixonColesModel(
        historical_results(), versions, clock=lambda: NOW
    )
    with (
        patch.object(UrllibJsonTransport, "get_json", return_value=provider_payload(count)),
        pytest.raises(InsufficientTrainingDataError),
    ):
        trainer.execute(ApiFootballTrainingScope(39, 2024, START, END), config())
    assert versions.items == {}


def test_reference_time_before_scope_end_fails_before_acquisition() -> None:
    versions = MemoryVersions()
    trainer = TrainApiFootballDixonColesModel(
        historical_results(), versions, clock=lambda: NOW
    )
    with (
        patch.object(UrllibJsonTransport, "get_json") as request,
        pytest.raises(ValueError, match="reference_time"),
    ):
        trainer.execute(
            ApiFootballTrainingScope(39, 2024, START, END),
            config(reference_time=END - timedelta(seconds=1)),
        )
    request.assert_not_called()


def test_persistence_failure_does_not_change_existing_active_model() -> None:
    existing, _ = _trusted_artifact_for_test()
    active = MemoryActive()
    active.items[SCOPE] = ActiveDixonColesModel(
        SCOPE, existing.model_version_id, NOW, 1
    )
    trainer = TrainApiFootballDixonColesModel(
        historical_results(), FailingVersions(), clock=lambda: NOW
    )
    with (
        patch.object(UrllibJsonTransport, "get_json", return_value=provider_payload()),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        trainer.execute(ApiFootballTrainingScope(39, 2024, START, END), config())
    assert active.get_active(SCOPE).model_version_id == existing.model_version_id


def test_activation_load_and_same_target_retry_are_version_bearing() -> None:
    versions, active = MemoryVersions(), MemoryActive()
    trainer = TrainApiFootballDixonColesModel(
        historical_results(), versions, clock=lambda: NOW
    )
    with patch.object(UrllibJsonTransport, "get_json", return_value=provider_payload()):
        version = trainer.execute(ApiFootballTrainingScope(39, 2024, START, END), config())
    activator = ActivateDixonColesModel(versions, active, clock=lambda: NOW)
    first = activator.execute(
        SCOPE,
        target_model_version_id=version.model_version_id,
        expected_current_model_version_id=None,
    )
    retry = activator.execute(
        SCOPE,
        target_model_version_id=version.model_version_id,
        expected_current_model_version_id="lost-acknowledgement-old-value",
    )
    assert retry == first
    assert retry.generation == 1
    loaded = LoadActiveDixonColesModel(versions, active).execute(SCOPE)
    assert loaded.model_version_id == version.model_version_id
    assert loaded.scope == SCOPE
    selected = LoadActiveDixonColesModel(versions, active).execute_with_selection(SCOPE)
    assert selected.loaded.model_version_id == loaded.model_version_id
    assert selected.loaded.scope == loaded.scope
    assert selected.loaded.provenance == loaded.provenance
    assert selected.generation == first.generation
    assert selected.activated_at == first.activated_at


def test_stale_activation_and_wrong_scope_fail_without_changing_active() -> None:
    versions, active = MemoryVersions(), MemoryActive()
    trainer = TrainApiFootballDixonColesModel(
        historical_results(), versions, clock=lambda: NOW
    )
    with patch.object(UrllibJsonTransport, "get_json", return_value=provider_payload()):
        version = trainer.execute(ApiFootballTrainingScope(39, 2024, START, END), config())
    activator = ActivateDixonColesModel(versions, active, clock=lambda: NOW)
    activator.execute(
        SCOPE,
        target_model_version_id=version.model_version_id,
        expected_current_model_version_id=None,
    )
    wrong = DixonColesModelScope("api-football", "api-football", 40, 2024)
    with pytest.raises(ValueError, match="different scope"):
        activator.execute(
            wrong,
            target_model_version_id=version.model_version_id,
            expected_current_model_version_id=None,
        )
    assert active.get_active(SCOPE).model_version_id == version.model_version_id


def test_corrupt_active_artifact_fails_closed_without_fallback() -> None:
    versions, active = MemoryVersions(), MemoryActive()
    trainer = TrainApiFootballDixonColesModel(
        historical_results(), versions, clock=lambda: NOW
    )
    with patch.object(UrllibJsonTransport, "get_json", return_value=provider_payload()):
        version = trainer.execute(ApiFootballTrainingScope(39, 2024, START, END), config())
    artifact = version.artifact
    corrupt = _create_dixon_coles_model_artifact(
        model_version_id=artifact.model_version_id,
        provenance=artifact.provenance,
        python_version=artifact.python_version,
        numpy_version=artifact.numpy_version,
        scipy_version=artifact.scipy_version,
        artifact_sha256=artifact.artifact_sha256,
        artifact_bytes=artifact.artifact_bytes + b"corrupt",
    )
    versions.items[artifact.model_version_id] = replace(version, artifact=corrupt)
    active.items[SCOPE] = ActiveDixonColesModel(SCOPE, artifact.model_version_id, NOW, 1)
    with pytest.raises(ValueError, match="digest"):
        LoadActiveDixonColesModel(versions, active).execute(SCOPE)
