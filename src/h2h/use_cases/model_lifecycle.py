"""Synchronous API-Football Dixon-Coles model lifecycle use cases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from h2h.domain.fixture_identity import API_FOOTBALL_PROVIDER
from h2h.domain.model_lifecycle import (
    ActiveDixonColesModel,
    DixonColesModelScope,
    DixonColesModelVersion,
    DixonColesTrainingConfig,
    LoadedDixonColesModelVersion,
    ValidatedActiveDixonColesModel,
)
from h2h.persistence.model_lifecycle import (
    ActiveDixonColesModelRepository,
    ActiveModelUnavailableError,
    DixonColesModelVersionRepository,
)
from h2h.quant.dixon_coles_artifact import (
    DixonColesArtifactCodecV1,
    _trusted_candidate_from_training,
)
from h2h.use_cases.api_football_training import (
    ApiFootballHistoricalResults,
    ApiFootballTrainingScope,
    fit_api_football_dixon_coles,
)


class InsufficientTrainingDataError(ValueError):
    """Trusted acquisition succeeded but cannot satisfy the requested fit."""


def _utc_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime):
        raise TypeError("clock must return a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


class TrainApiFootballDixonColesModel:
    """Acquire, fit, serialize and persist one inactive model version."""

    def __init__(
        self,
        historical_results: ApiFootballHistoricalResults,
        versions: DixonColesModelVersionRepository,
        *,
        clock: Callable[[], datetime],
        codec: DixonColesArtifactCodecV1 | None = None,
    ) -> None:
        if not isinstance(historical_results, ApiFootballHistoricalResults):
            raise TypeError("historical_results must be an ApiFootballHistoricalResults")
        self._historical_results = historical_results
        self._versions = versions
        self._clock = clock
        self._codec = codec or DixonColesArtifactCodecV1()

    def execute(
        self,
        scope: ApiFootballTrainingScope,
        config: DixonColesTrainingConfig,
        *,
        target_scope: DixonColesModelScope | None = None,
    ) -> DixonColesModelVersion:
        if not isinstance(scope, ApiFootballTrainingScope):
            raise TypeError("scope must be an ApiFootballTrainingScope")
        if not isinstance(config, DixonColesTrainingConfig):
            raise TypeError("config must be a DixonColesTrainingConfig")
        if config.reference_time < scope.end_at:
            raise ValueError("reference_time must be at or after scope.end_at")
        resolved_target = target_scope or DixonColesModelScope(
            API_FOOTBALL_PROVIDER,
            API_FOOTBALL_PROVIDER,
            scope.league_id,
            scope.season,
        )
        _require_api_football_scope(resolved_target)
        if resolved_target.league_id != scope.league_id:
            raise ValueError("target model league must match the trusted training league")
        dataset = self._historical_results.acquire(scope)
        if len(dataset) < config.min_matches:
            raise InsufficientTrainingDataError(
                f"trusted dataset has {len(dataset)} matches; {config.min_matches} required"
            )
        model = fit_api_football_dixon_coles(
            dataset,
            reference_time=config.reference_time,
            xi=config.xi,
            ridge=config.ridge,
            min_matches=config.min_matches,
        )
        if model.fitted_matches != len(dataset):
            raise InsufficientTrainingDataError(
                "accepted match count does not equal fitted match count"
            )
        candidate = _trusted_candidate_from_training(
            dataset=dataset,
            scope=scope,
            config=config,
            model=model,
            trained_at=_utc_now(self._clock),
            target_scope=resolved_target,
        )
        return self._versions.add(self._codec.encode(candidate))


class ActivateDixonColesModel:
    """Validate a persisted artifact and atomically activate it for its scope."""

    def __init__(
        self,
        versions: DixonColesModelVersionRepository,
        active_models: ActiveDixonColesModelRepository,
        *,
        clock: Callable[[], datetime],
        codec: DixonColesArtifactCodecV1 | None = None,
    ) -> None:
        self._versions = versions
        self._active_models = active_models
        self._clock = clock
        self._codec = codec or DixonColesArtifactCodecV1()

    def execute(
        self,
        scope: DixonColesModelScope,
        *,
        target_model_version_id: str,
        expected_current_model_version_id: str | None,
    ) -> ActiveDixonColesModel:
        _require_api_football_scope(scope)
        version = self._versions.get(target_model_version_id)
        if version is None:
            raise ActiveModelUnavailableError(
                f"model version {target_model_version_id!r} does not exist"
            )
        if version.scope != scope:
            raise ValueError("target model version belongs to a different scope")
        self._codec.decode(version.artifact)
        return self._active_models.compare_and_swap(
            scope,
            target_model_version_id=target_model_version_id,
            expected_current_model_version_id=expected_current_model_version_id,
            activated_at=_utc_now(self._clock),
        )


class LoadActiveDixonColesModel:
    """Resolve and validate the authoritative active model from PostgreSQL."""

    def __init__(
        self,
        versions: DixonColesModelVersionRepository,
        active_models: ActiveDixonColesModelRepository,
        *,
        codec: DixonColesArtifactCodecV1 | None = None,
    ) -> None:
        self._versions = versions
        self._active_models = active_models
        self._codec = codec or DixonColesArtifactCodecV1()

    def execute(self, scope: DixonColesModelScope) -> LoadedDixonColesModelVersion:
        return self.execute_with_selection(scope).loaded

    def execute_with_selection(self, scope: DixonColesModelScope) -> ValidatedActiveDixonColesModel:
        """Return the validated model and exact active-pointer provenance."""
        _require_api_football_scope(scope)
        active = self._active_models.get_active(scope)
        if active is None:
            raise ActiveModelUnavailableError("no active model exists for the requested scope")
        version = self._versions.get(active.model_version_id)
        if version is None:
            raise ActiveModelUnavailableError("active model version is missing")
        if version.scope != scope:
            raise ActiveModelUnavailableError("active model version belongs to another scope")
        loaded = self._codec.decode(version.artifact)
        if loaded.model_version_id != active.model_version_id or loaded.scope != active.scope:
            raise ActiveModelUnavailableError("validated model contradicts active selection")
        return ValidatedActiveDixonColesModel(
            loaded=loaded,
            generation=active.generation,
            activated_at=active.activated_at,
        )


def _require_api_football_scope(scope: DixonColesModelScope) -> None:
    if not isinstance(scope, DixonColesModelScope):
        raise TypeError("scope must be a DixonColesModelScope")
    if scope.provider != API_FOOTBALL_PROVIDER or (
        scope.team_id_namespace != API_FOOTBALL_PROVIDER
    ):
        raise ValueError("Task #8 supports only the api-football provider and namespace")
