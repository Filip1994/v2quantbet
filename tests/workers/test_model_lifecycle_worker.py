from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from h2h.domain.model_coverage import ModelCoverageStatus, ProductionTrainingPolicy
from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.persistence.postgres_model_coverage import ModelCoverageRecord
from h2h.quant.dixon_coles import DixonColesFitAbortedError
from h2h.use_cases.model_lifecycle import InsufficientTrainingDataError
from h2h.workers.model_lifecycle import ModelLifecycleWorker, ModelQualityError


NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)


def record(league: int, season: int = 2026) -> ModelCoverageRecord:
    return ModelCoverageRecord(
        DixonColesModelScope("api-football", "api-football", league, season),
        ModelCoverageStatus.TRAINING_PENDING,
        NOW,
        NOW,
        NOW,
        1,
        None,
        None,
        None,
        None,
    )


class CoverageFake:
    def __init__(self, records: list[ModelCoverageRecord]) -> None:
        self.records = records
        self.active: list[DixonColesModelScope] = []
        self.insufficient: list[DixonColesModelScope] = []
        self.failed: list[DixonColesModelScope] = []
        self.released: list[DixonColesModelScope] = []
        self.claim_limits: list[int] = []

    def refresh_inventory(self, _policy, *, now):
        return len(self.records)

    def claim_training_scopes(self, *, now, limit):
        self.claim_limits.append(limit)
        claimed = tuple(self.records[:limit])
        self.records = self.records[limit:]
        return claimed

    def required_team_ids(self, _scope, *, now):
        return (10, 20)

    def mark_active(self, scope, **_kwargs):
        self.active.append(scope)

    def mark_insufficient(self, scope, _error, **_kwargs):
        self.insufficient.append(scope)

    def mark_failed(self, scope, _error, **_kwargs):
        self.failed.append(scope)

    def release_pending(self, scope, **_kwargs):
        self.released.append(scope)

    def has_pending(self, *, now):
        return bool(self.records)


class ActiveFake:
    def __init__(self, current=None) -> None:
        self.current = current

    def get_active(self, _scope):
        return self.current


class ActivatorFake:
    def __init__(self, generation: int = 1) -> None:
        self.calls = []
        self.generation = generation

    def execute(self, scope, **kwargs):
        self.calls.append((scope, kwargs))
        return SimpleNamespace(
            model_version_id=kwargs["target_model_version_id"],
            generation=self.generation,
        )


def version(scope: DixonColesModelScope, version_id: str = "model-v1"):
    provenance = SimpleNamespace(accepted_match_count=120, fitted_match_count=120)
    return SimpleNamespace(
        model_version_id=version_id,
        artifact=SimpleNamespace(provenance=provenance, scope=scope),
    )


def worker(coverage, trainer, active, activator, usage, *, max_scopes=1, max_requests=2, stop=lambda: False):
    result = ModelLifecycleWorker(
        coverage,
        trainer,
        activator,
        active,
        ProductionTrainingPolicy(),
        max_scopes=max_scopes,
        max_provider_requests=max_requests,
        max_wall_seconds=45,
        training_requests_used=lambda: usage[0],
        should_stop=stop,
        clock=lambda: NOW,
    )
    result._validate = lambda *_args: None
    return result


def test_training_cycle_claims_only_configured_scope_bound() -> None:
    coverage = CoverageFake([record(39), record(40), record(41)])
    usage = [0]
    trainer_calls = []

    class Trainer:
        def execute(self, _training_scope, _config, *, target_scope, should_abort):
            trainer_calls.append(target_scope)
            usage[0] += 1
            return version(target_scope)

    lifecycle = worker(
        coverage,
        Trainer(),
        ActiveFake(),
        ActivatorFake(),
        usage,
        max_scopes=2,
        max_requests=2,
    )
    cycle = lifecycle.run_once()

    assert coverage.claim_limits == [2]
    assert len(trainer_calls) == 2
    assert cycle.claimed_scopes == cycle.activated_scopes == 2
    assert cycle.provider_requests_used == 2
    assert cycle.pending_work


def test_cycle_provider_budget_stops_before_another_historical_request() -> None:
    coverage = CoverageFake([record(39), record(40)])
    usage = [0]

    class Trainer:
        calls = 0

        def execute(self, *_args, **_kwargs):
            self.calls += 1
            usage[0] += 1
            raise InsufficientTrainingDataError("not enough completed matches")

    trainer = Trainer()
    cycle = worker(
        coverage,
        trainer,
        ActiveFake(),
        ActivatorFake(),
        usage,
        max_scopes=2,
        max_requests=1,
    ).run_once()

    assert trainer.calls == 1
    assert cycle.provider_requests_used == 1
    assert coverage.failed == [record(39).scope]
    assert coverage.released == [record(40).scope]


def test_valid_new_model_replaces_active_pointer_with_cas_generation() -> None:
    coverage = CoverageFake([record(39)])
    usage = [0]
    old = SimpleNamespace(model_version_id="model-old", generation=4)
    activator = ActivatorFake(generation=5)

    class Trainer:
        def execute(self, _scope, _config, *, target_scope, should_abort):
            usage[0] += 1
            return version(target_scope, "model-new")

    cycle = worker(
        coverage,
        Trainer(),
        ActiveFake(old),
        activator,
        usage,
    ).run_once()

    assert cycle.activated_scopes == 1
    assert activator.calls[0][1] == {
        "target_model_version_id": "model-new",
        "expected_current_model_version_id": "model-old",
    }
    assert coverage.active == [record(39).scope]


def test_shutdown_releases_claim_without_training_or_tight_failure() -> None:
    coverage = CoverageFake([record(39), record(40)])
    usage = [0]

    class Trainer:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("training must not start during shutdown")

    cycle = worker(
        coverage,
        Trainer(),
        ActiveFake(),
        ActivatorFake(),
        usage,
        max_scopes=2,
        stop=lambda: True,
    ).run_once()

    assert cycle.interrupted
    assert coverage.released == [record(39).scope, record(40).scope]
    assert not coverage.failed


def test_insufficient_data_never_reaches_activation() -> None:
    coverage = CoverageFake([record(39)])
    usage = [0]
    activator = ActivatorFake()

    class Trainer:
        def execute(self, *_args, **_kwargs):
            usage[0] += 1
            raise InsufficientTrainingDataError("sample below minimum")

    cycle = worker(
        coverage,
        Trainer(),
        ActiveFake(),
        activator,
        usage,
    ).run_once()

    assert cycle.insufficient_scopes == 1
    assert coverage.insufficient == [record(39).scope]
    assert activator.calls == []


def test_wall_clock_abort_fails_scope_and_returns_control() -> None:
    coverage = CoverageFake([record(39)])
    usage = [0]
    elapsed = [0.0]

    class Trainer:
        def execute(self, _scope, _config, *, target_scope, should_abort):
            assert target_scope == record(39).scope
            while not should_abort():
                elapsed[0] += 10.0
            raise DixonColesFitAbortedError(
                "Dixon-Coles fit aborted by shutdown or wall-clock guard"
            )

    lifecycle = worker(
        coverage,
        Trainer(),
        ActiveFake(),
        ActivatorFake(),
        usage,
    )
    lifecycle._monotonic = lambda: elapsed[0]

    cycle = lifecycle.run_once()

    assert cycle.wall_budget_exhausted
    assert cycle.failed_scopes == 1
    assert not cycle.interrupted
    assert coverage.failed == [record(39).scope]
    assert elapsed[0] >= 45.0


def test_invalid_artifact_quality_gate_never_changes_active_pointer() -> None:
    coverage = CoverageFake([record(39)])
    usage = [0]
    activator = ActivatorFake()

    class Trainer:
        def execute(self, _scope, _config, *, target_scope, should_abort):
            usage[0] += 1
            return version(target_scope)

    lifecycle = worker(
        coverage,
        Trainer(),
        ActiveFake(),
        activator,
        usage,
    )

    def invalid(*_args):
        raise ModelQualityError("probabilities are not normalized")

    lifecycle._validate = invalid
    cycle = lifecycle.run_once()

    assert cycle.failed_scopes == 1
    assert coverage.failed == [record(39).scope]
    assert activator.calls == []
