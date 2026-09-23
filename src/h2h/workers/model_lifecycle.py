"""Bounded, fair production Dixon-Coles coverage worker."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isclose, isfinite
from time import monotonic

import numpy as np

from h2h.domain.model_coverage import ProductionTrainingPolicy
from h2h.domain.model_lifecycle import DixonColesTrainingConfig
from h2h.odds import ApiBudgetExceededError
from h2h.persistence.postgres_model_coverage import PostgreSQLModelCoverageRepository
from h2h.persistence.postgres_model_lifecycle import PostgreSQLActiveDixonColesModelRepository
from h2h.quant import DixonColesFitError
from h2h.quant.dixon_coles import DixonColesFitAbortedError
from h2h.quant.dixon_coles_artifact import DixonColesArtifactCodecV1
from h2h.use_cases.api_football_training import ApiFootballTrainingScope
from h2h.use_cases.model_lifecycle import (
    ActivateDixonColesModel,
    InsufficientTrainingDataError,
    TrainApiFootballDixonColesModel,
)


LOGGER = logging.getLogger("quantbet.model_lifecycle")
WORKER_NAME = "model_lifecycle"


class ModelQualityError(ValueError):
    """A fitted artifact failed the production activation gate."""


@dataclass(frozen=True, slots=True)
class ModelLifecycleCycle:
    eligible_scopes: int
    claimed_scopes: int
    activated_scopes: int
    insufficient_scopes: int
    failed_scopes: int
    provider_requests_used: int
    accepted_matches: int
    fitted_matches: int
    duration_seconds: float
    pending_work: bool
    interrupted: bool
    wall_budget_exhausted: bool


class ModelLifecycleWorker:
    def __init__(
        self,
        coverage: PostgreSQLModelCoverageRepository,
        trainer: TrainApiFootballDixonColesModel,
        activator: ActivateDixonColesModel,
        active_models: PostgreSQLActiveDixonColesModelRepository,
        policy: ProductionTrainingPolicy,
        *,
        max_scopes: int,
        max_provider_requests: int,
        max_wall_seconds: float,
        training_requests_used: Callable[[], int],
        should_stop: Callable[[], bool],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic_clock: Callable[[], float] = monotonic,
        codec: DixonColesArtifactCodecV1 | None = None,
    ) -> None:
        if max_scopes <= 0 or max_provider_requests <= 0 or max_wall_seconds <= 0:
            raise ValueError("model lifecycle work bounds must be positive")
        self._coverage = coverage
        self._trainer = trainer
        self._activator = activator
        self._active_models = active_models
        self._policy = policy
        self._max_scopes = max_scopes
        self._max_provider_requests = max_provider_requests
        self._max_wall_seconds = max_wall_seconds
        self._training_requests_used = training_requests_used
        self._should_stop = should_stop
        self._clock = clock
        self._monotonic = monotonic_clock
        self._codec = codec or DixonColesArtifactCodecV1()
        self._has_pending = False

    @property
    def has_pending(self) -> bool:
        return self._has_pending

    def run_once(self) -> ModelLifecycleCycle:
        started = self._monotonic()
        now = self._clock().astimezone(UTC)
        recover = getattr(self._coverage, "recover_abandoned_claims", None)
        if recover is not None:
            recover(now=now, lease_seconds=self._max_wall_seconds * 2)
        eligible = self._coverage.refresh_inventory(self._policy, now=now)
        claimed = self._coverage.claim_training_scopes(now=now, limit=self._max_scopes)
        request_start = self._training_requests_used()
        activated = 0
        insufficient = 0
        failed = 0
        accepted = 0
        fitted = 0
        interrupted = False
        wall_exhausted = False
        handled_scopes = set()

        def training_should_abort() -> bool:
            return self._should_stop() or (
                self._monotonic() - started >= self._max_wall_seconds
            )

        for record in claimed:
            scope_started = self._monotonic()
            handled_scopes.add(record.scope)
            if self._should_stop():
                interrupted = True
                self._coverage.release_pending(
                    record.scope,
                    now=self._clock(),
                    reason="shutdown requested before model training",
                )
                break
            if self._monotonic() - started >= self._max_wall_seconds:
                wall_exhausted = True
                self._coverage.release_pending(
                    record.scope,
                    now=self._clock(),
                    reason="model training wall-clock budget exhausted",
                )
                break

            best_accepted = 0
            last_insufficient: BaseException | None = None
            try:
                required_teams = self._coverage.required_team_ids(record.scope, now=now)
                if len(required_teams) < 2:
                    raise InsufficientTrainingDataError(
                        "scope has fewer than two teams awaiting prediction"
                    )
                window_start, window_end = self._policy.training_window(now)
                trained = None
                for training_season in self._policy.allowed_training_seasons(
                    record.scope.season
                ):
                    used = self._training_requests_used() - request_start
                    if used >= self._max_provider_requests:
                        raise ApiBudgetExceededError(
                            "model-training cycle provider-request budget exhausted"
                        )
                    training_scope = ApiFootballTrainingScope(
                        league_id=record.scope.league_id,
                        season=training_season,
                        start_at=window_start,
                        end_at=window_end,
                    )
                    config = DixonColesTrainingConfig(
                        reference_time=window_end,
                        xi=self._policy.xi,
                        ridge=self._policy.ridge,
                        min_matches=self._policy.min_matches,
                        trainer_code_version=self._policy.provenance_trainer_version,
                    )
                    try:
                        candidate = self._trainer.execute(
                            training_scope,
                            config,
                            target_scope=record.scope,
                            should_abort=training_should_abort,
                        )
                        best_accepted = max(
                            best_accepted,
                            candidate.artifact.provenance.accepted_match_count,
                        )
                        self._validate(candidate, record.scope, required_teams)
                    except (InsufficientTrainingDataError, ModelQualityError) as exc:
                        if isinstance(exc, InsufficientTrainingDataError):
                            best_accepted = max(
                                best_accepted,
                                exc.accepted_match_count or 0,
                            )
                        last_insufficient = exc
                        continue
                    trained = candidate
                    break
                if trained is None:
                    raise last_insufficient or InsufficientTrainingDataError(
                        "no allowed training season produced a valid model"
                    )
                current = self._active_models.get_active(record.scope)
                active = self._activator.execute(
                    record.scope,
                    target_model_version_id=trained.model_version_id,
                    expected_current_model_version_id=(
                        None if current is None else current.model_version_id
                    ),
                )
                provenance = trained.artifact.provenance
                accepted += provenance.accepted_match_count
                fitted += provenance.fitted_match_count
                activated += 1
                self._coverage.mark_active(
                    record.scope,
                    model_version_id=active.model_version_id,
                    generation=active.generation,
                    accepted_matches=provenance.accepted_match_count,
                    fitted_matches=provenance.fitted_match_count,
                    duration_seconds=self._monotonic() - scope_started,
                    now=self._clock(),
                )
                LOGGER.info(
                    "model scope activated",
                    extra={
                        "model_scope": self._scope_key(record.scope),
                        "model_version_id": active.model_version_id,
                        "active_generation": active.generation,
                        "accepted_matches": provenance.accepted_match_count,
                        "fitted_matches": provenance.fitted_match_count,
                    },
                )
            except DixonColesFitAbortedError as exc:
                if self._should_stop():
                    interrupted = True
                    self._coverage.release_pending(
                        record.scope,
                        now=self._clock(),
                        reason="shutdown requested during model training",
                    )
                else:
                    wall_exhausted = True
                    failed += 1
                    self._coverage.mark_failed(
                        record.scope,
                        exc,
                        duration_seconds=self._monotonic() - scope_started,
                        now=self._clock(),
                    )
                    LOGGER.warning(
                        "model scope training exceeded wall-clock budget",
                        extra={
                            "model_scope": self._scope_key(record.scope),
                            "error_class": type(exc).__name__,
                        },
                    )
                break
            except InsufficientTrainingDataError as exc:
                insufficient += 1
                self._coverage.mark_insufficient(
                    record.scope,
                    exc,
                    accepted_matches=best_accepted,
                    duration_seconds=self._monotonic() - scope_started,
                    now=self._clock(),
                )
                LOGGER.info(
                    "model scope has insufficient data",
                    extra={
                        "model_scope": self._scope_key(record.scope),
                        "accepted_matches": best_accepted,
                        "error_class": type(exc).__name__,
                    },
                )
            except (ApiBudgetExceededError, DixonColesFitError, TypeError, ValueError, RuntimeError) as exc:
                failed += 1
                self._coverage.mark_failed(
                    record.scope,
                    exc,
                    duration_seconds=self._monotonic() - scope_started,
                    now=self._clock(),
                )
                LOGGER.warning(
                    "model scope training failed",
                    extra={
                        "model_scope": self._scope_key(record.scope),
                        "error_class": type(exc).__name__,
                    },
                )
                if isinstance(exc, ApiBudgetExceededError):
                    break

        for record in claimed:
            if record.scope not in handled_scopes:
                self._coverage.release_pending(
                    record.scope,
                    now=self._clock(),
                    reason="cycle ended before claimed scope started",
                )
        provider_requests = self._training_requests_used() - request_start
        self._has_pending = self._coverage.has_pending(now=self._clock())
        cycle = ModelLifecycleCycle(
            eligible_scopes=eligible,
            claimed_scopes=len(claimed),
            activated_scopes=activated,
            insufficient_scopes=insufficient,
            failed_scopes=failed,
            provider_requests_used=provider_requests,
            accepted_matches=accepted,
            fitted_matches=fitted,
            duration_seconds=self._monotonic() - started,
            pending_work=self._has_pending,
            interrupted=interrupted,
            wall_budget_exhausted=wall_exhausted,
        )
        LOGGER.info(
            "model lifecycle cycle outcomes",
            extra={
                "worker": WORKER_NAME,
                "eligible_model_scopes": cycle.eligible_scopes,
                "claimed_model_scopes": cycle.claimed_scopes,
                "activated_model_scopes": cycle.activated_scopes,
                "insufficient_data_scopes": cycle.insufficient_scopes,
                "training_failed_scopes": cycle.failed_scopes,
                "training_provider_requests": cycle.provider_requests_used,
                "accepted_matches": cycle.accepted_matches,
                "fitted_matches": cycle.fitted_matches,
                "duration_seconds": cycle.duration_seconds,
                "pending_work": cycle.pending_work,
            },
        )
        return cycle

    def _validate(self, version: object, scope: object, required_teams: tuple[int, ...]) -> None:
        artifact = version.artifact  # type: ignore[attr-defined]
        loaded = self._codec.decode(artifact)
        if loaded.scope != scope or artifact.scope != scope:
            raise ModelQualityError("decoded artifact does not match requested target scope")
        provenance = loaded.provenance
        if provenance.fitted_match_count < self._policy.min_matches:
            raise ModelQualityError("fitted match count is below policy minimum")
        counts = dict(provenance.team_match_counts)
        uncovered = [
            team_id
            for team_id in required_teams
            if counts.get(team_id, 0) < self._policy.min_team_matches
        ]
        if uncovered:
            raise InsufficientTrainingDataError(
                f"intended fixture teams lack minimum coverage: {uncovered[:10]}",
                accepted_match_count=provenance.accepted_match_count,
            )
        model = loaded.model
        scalars = (model.intercept, model.home_advantage, model.rho, model.xi, model.objective)
        if not all(isfinite(float(value)) for value in scalars):
            raise ModelQualityError("model contains non-finite scalar parameters")
        if not np.all(np.isfinite(model.attacks)) or not np.all(np.isfinite(model.defenses)):
            raise ModelQualityError("model contains non-finite team parameters")
        for index, home_id in enumerate(required_teams):
            away_id = required_teams[(index + 1) % len(required_teams)]
            expected = model.expected_goals(home_id, away_id)
            if not all(isfinite(value) and value > 0 for value in expected):
                raise ModelQualityError("expected-goals generation failed quality checks")
            matrix = model.score_matrix(home_id, away_id)
            if not np.all(np.isfinite(matrix)) or not isclose(
                float(matrix.sum()), 1.0, rel_tol=0.0, abs_tol=1e-10
            ):
                raise ModelQualityError("score probabilities are not finite and normalized")
            probabilities = model.market_probabilities(home_id, away_id)
            if set(probabilities) != {"OVER_2_5", "UNDER_2_5", "BTTS_YES"}:
                raise ModelQualityError("canonical market probabilities are incomplete")
            if not all(isfinite(value) and 0 <= value <= 1 for value in probabilities.values()):
                raise ModelQualityError("market probabilities are invalid")
            if not isclose(
                probabilities["OVER_2_5"] + probabilities["UNDER_2_5"],
                1.0,
                rel_tol=0.0,
                abs_tol=1e-10,
            ):
                raise ModelQualityError("over/under probabilities are not normalized")

    @staticmethod
    def _scope_key(scope: object) -> str:
        return (
            f"{scope.provider}:{scope.team_id_namespace}:"  # type: ignore[attr-defined]
            f"{scope.league_id}:{scope.season}"  # type: ignore[attr-defined]
        )
