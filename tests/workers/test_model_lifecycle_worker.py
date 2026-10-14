from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from threading import Event

import pytest

from h2h.domain.model_coverage import ModelCoverageStatus, ProductionTrainingPolicy
from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.persistence.postgres_model_coverage import ModelCoverageRecord
from h2h.quant.dixon_coles import DixonColesFitAbortedError, DixonColesFitError
from h2h.use_cases.model_lifecycle import InsufficientTrainingDataError
from h2h.workers.model_lifecycle import ModelLifecycleWorker, ModelQualityError
from h2h.workers.orchestrator import ProductionOrchestrator, ScheduledJob


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
        self.failure_details = []
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
        self.failure_details.append((_error, _kwargs))

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
    provenance = SimpleNamespace(accepted_match_count=120, fitted_match_count=120,
                                 dataset_sha256="a" * 64)
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


def test_wall_clock_abort_does_not_starve_following_scheduler_jobs() -> None:
    coverage = CoverageFake([record(39)])
    usage = [0]
    elapsed = [0.0]
    stop = Event()
    later_runs: list[str] = []

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

    class Runtime:
        def worker_started(self, *_args, **_kwargs):
            return None

        def worker_succeeded(self, *_args, **_kwargs):
            return None

        def worker_failed(self, *_args, **_kwargs):
            raise AssertionError("model timeout must be contained by model lifecycle")

    def run_after_model(name: str) -> None:
        later_runs.append(name)
        if name == "results":
            stop.set()

    jobs = (
        ScheduledJob("model_lifecycle", 60, lifecycle.run_once),
        ScheduledJob("opportunity", 60, lambda: run_after_model("opportunity")),
        ScheduledJob("monitoring", 60, lambda: run_after_model("monitoring")),
        ScheduledJob("results", 60, lambda: run_after_model("results")),
    )
    ProductionOrchestrator(
        jobs,
        Runtime(),  # type: ignore[arg-type]
        instance_id="test",
        stop=stop,
        tick_seconds=1,
        leader_healthy=lambda: True,
    ).run_forever()

    assert later_runs == ["opportunity", "monitoring", "results"]
    assert coverage.failed == [record(39).scope]


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


def test_failed_510_retrain_preserves_active_model_and_other_scope_trains(caplog) -> None:
    failed_record = replace(record(510), active_model_version_id="last-good",
                            active_generation=4, failed_dataset_sha256="b" * 64,
                            failure_streak=1)
    coverage = CoverageFake([failed_record, record(39)])
    usage = [0]
    activator = ActivatorFake()

    class Trainer:
        def execute(self, _scope, _config, *, target_scope, should_abort, **kwargs):
            usage[0] += 1
            if target_scope.league_id == 510:
                assert kwargs["failure_streak"] == 1
                error = DixonColesFitError("ABNORMAL")
                error.dataset_sha256 = "b" * 64
                error.training_sample_size = 99
                error.optimizer_status = 2
                raise error
            return version(target_scope)

    cycle = worker(coverage, Trainer(), ActiveFake(SimpleNamespace(
        model_version_id="last-good", generation=4)), activator, usage,
        max_scopes=2).run_once()
    assert cycle.failed_scopes == cycle.activated_scopes == 1
    assert coverage.failed == [failed_record.scope]
    assert coverage.active == [record(39).scope]
    assert coverage.failure_details[0][1]["retry_after"] == timedelta(hours=6)
    assert all(call[0] != failed_record.scope for call in activator.calls)
    warning = next(item for item in caplog.records if item.message == "model scope training failed")
    assert warning.canonical_scope_id == "api-football:api-football:510:2026"
    assert warning.dataset_fingerprint == "b" * 64
    assert warning.fallback_active is True


@pytest.mark.parametrize(("streak", "delay"), [
    (0, timedelta(hours=1)),
    (1, timedelta(hours=6)),
    (2, timedelta(days=1)),
])
def test_optimizer_failure_backoff_is_bounded(streak, delay) -> None:
    previous = "b" * 64 if streak else None
    coverage = CoverageFake([replace(record(510), failed_dataset_sha256=previous,
                                     failure_streak=streak)])
    class Trainer:
        def execute(self, *_args, **_kwargs):
            error = DixonColesFitError("ABNORMAL")
            error.dataset_sha256 = "b" * 64
            raise error
    worker(coverage, Trainer(), ActiveFake(), ActivatorFake(), [0]).run_once()
    assert coverage.failure_details[0][1]["retry_after"] == delay


def test_transient_optimizer_failure_can_activate_on_next_claim() -> None:
    coverage = CoverageFake([record(510)])
    usage = [0]
    activator = ActivatorFake()
    class Trainer:
        calls = 0
        def execute(self, _scope, _config, *, target_scope, should_abort, **_kwargs):
            self.calls += 1
            usage[0] += 1
            if self.calls == 1:
                error = DixonColesFitError("ABNORMAL")
                error.dataset_sha256 = "b" * 64
                raise error
            return version(target_scope, "new-good")
    trainer = Trainer()
    lifecycle = worker(coverage, trainer, ActiveFake(), activator, usage)
    assert lifecycle.run_once().failed_scopes == 1
    coverage.records = [replace(record(510), failed_dataset_sha256="b" * 64,
                                failure_streak=1)]
    assert lifecycle.run_once().activated_scopes == 1
    assert trainer.calls == 2
    assert activator.calls[0][0] == record(510).scope
