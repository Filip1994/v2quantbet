"""Persistence contracts and lifecycle-level model errors."""

from __future__ import annotations

from typing import Protocol

from h2h.domain.model_lifecycle import (
    ActiveDixonColesModel,
    DixonColesModelArtifact,
    DixonColesModelScope,
    DixonColesModelVersion,
)


class ModelPersistenceConflictError(ValueError):
    """An immutable model-version identity was reused inconsistently."""


class ModelActivationConflictError(ValueError):
    """The active model changed after the caller observed it."""


class ActiveModelUnavailableError(RuntimeError):
    """No usable active model exists for the requested scope."""


class DixonColesModelVersionRepository(Protocol):
    def add(self, artifact: DixonColesModelArtifact) -> DixonColesModelVersion: ...

    def get(self, model_version_id: str) -> DixonColesModelVersion | None: ...

    def list_for_scope(
        self, scope: DixonColesModelScope
    ) -> tuple[DixonColesModelVersion, ...]: ...


class ActiveDixonColesModelRepository(Protocol):
    def get_active(self, scope: DixonColesModelScope) -> ActiveDixonColesModel | None: ...

    def compare_and_swap(
        self,
        scope: DixonColesModelScope,
        *,
        target_model_version_id: str,
        expected_current_model_version_id: str | None,
        activated_at: object,
    ) -> ActiveDixonColesModel: ...

    def list_active(self) -> tuple[ActiveDixonColesModel, ...]: ...
