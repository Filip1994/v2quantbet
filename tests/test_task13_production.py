from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from urllib.request import urlopen

import pytest

from h2h.api.health import HealthService, RuntimeHealthState
from h2h.config import ConfigError, PilotScope, load_production_settings
from h2h.persistence.postgres_runtime import OpportunityFixture, WorkerStatus
from h2h.quant import DixonColesFitError
from h2h.production import build_production_application
from h2h.workers.opportunity import OpportunityWorker, PilotFixtureDiscovery, registration_request_id
from h2h.workers.orchestrator import ProductionOrchestrator, ScheduledJob

from tests.test_config import lifecycle_environment, registration_environment


def production_environment() -> dict[str, str]:
    values = registration_environment()
    values.update(lifecycle_environment())
    values.update(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "INFO",
            "API_FOOTBALL_KEY": "test-key",
            "DATABASE_URL": "postgresql://example/quantbet",
            "QUANTBET_PILOT_SCOPES": "39:2026,140:2026",
            "QUANTBET_PILOT_BOOKMAKER_ID": "8",
            "QUANTBET_BANKROLL_BOOTSTRAP_MODE": "verify",
        }
    )
    return values


def test_production_config_is_complete_and_scoped() -> None:
    settings = load_production_settings(production_environment())
    assert settings.pilot_scopes == (PilotScope(39, 2026), PilotScope(140, 2026))
    assert settings.pilot_bookmaker_id == 8
    assert settings.discovery_interval_seconds == 900


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("QUANTBET_PILOT_SCOPES", ""),
        ("QUANTBET_PILOT_SCOPES", "broken"),
        ("QUANTBET_PILOT_BOOKMAKER_ID", "7"),
        ("QUANTBET_BANKROLL_BOOTSTRAP_MODE", "automatic"),
        ("APP_ENV", "development"),
        ("LOG_LEVEL", "VERBOSE"),
    ],
)
def test_production_config_rejects_partial_or_invalid_values(name: str, value: str) -> None:
    environment = production_environment()
    environment[name] = value
    with pytest.raises(ConfigError):
        load_production_settings(environment)


def test_optional_fixture_ids_accept_provider_and_canonical_forms() -> None:
    environment = production_environment()
    environment["QUANTBET_PILOT_FIXTURE_IDS"] = "123,api-football:456"
    assert load_production_settings(environment).pilot_fixture_ids == {123, 456}


def test_production_composition_shares_one_client_and_budget() -> None:
    application = build_production_application(load_production_settings(production_environment()))
    assert application.opportunity._source.client is application.client
    assert application.monitoring.refresh_odds._source.client is application.client
    assert application.results.reconcile._source._client is application.client
    assert application.client.transport.transport.budget is application.budget
    durable = application.prediction.durable_discovery
    assert durable is not None
    provider_discovery = durable._discovery._discovery._discovery
    assert provider_discovery._client is application.client


def test_pilot_discovery_restricts_after_underlying_discovery() -> None:
    fixtures = (
        SimpleNamespace(competition_id=39, season=2026, provider_fixture_id=1),
        SimpleNamespace(competition_id=140, season=2026, provider_fixture_id=2),
    )
    underlying = SimpleNamespace(discover=lambda _start, _end: fixtures)
    discovery = PilotFixtureDiscovery(underlying, (PilotScope(39, 2026),), frozenset({1}))
    now = datetime.now(UTC)
    assert discovery.discover(now, now + timedelta(hours=1)) == (fixtures[0],)


class OpportunityRepositoryFake:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.fixture = OpportunityFixture(
            "api-football:123",
            SimpleNamespace(fixture_id="api-football:123"),
            39,
            2026,
            now + timedelta(hours=2),
            None,
        )
        self.bookmakers: list[int] = []

    def due_opportunity_fixtures(self, **_kwargs):
        return (self.fixture,)

    def item_retry_due(self, *_args, **_kwargs):
        return True

    def latest_complete_snapshot_ids(self, _fixture_id, bookmaker_id):
        self.bookmakers.append(bookmaker_id)
        return ("snapshot-a", "snapshot-b")

    def record_item_failure(self, *_args, **_kwargs):
        raise AssertionError("unexpected item failure")

    def clear_item_failure(self, *_args, **_kwargs):
        return None


def test_opportunity_pipeline_is_deterministic_and_one_bookmaker_only() -> None:
    repository = OpportunityRepositoryFake()
    requests: list[tuple[str, str]] = []
    quote_requests: list[dict[str, object]] = []

    def fetch_quotes(**kwargs):
        quote_requests.append(kwargs)
        return ()

    source = SimpleNamespace(fetch_quotes=fetch_quotes)
    ingestion = SimpleNamespace(ingest=lambda _quotes: 0)
    predictor = SimpleNamespace(
        execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction-1")
    )
    evaluator = SimpleNamespace(
        execute=lambda _prediction, snapshot: SimpleNamespace(evaluation_id=f"eval-{snapshot}")
    )

    def register(evaluation_id, request_id):
        requests.append((evaluation_id, request_id))
        pick = SimpleNamespace(pick_id="pick-1") if evaluation_id.endswith("a") else None
        return SimpleNamespace(pick=pick)

    worker = OpportunityWorker(
        repository,
        source,
        ingestion,
        predictor,
        evaluator,
        SimpleNamespace(execute=register),
        scopes=(PilotScope(39, 2026),),
        bookmaker_id=8,
        provider_fixture_ids=frozenset(),
        allowed_statuses=("NS",),
        usable_scopes=lambda: frozenset({PilotScope(39, 2026)}),
        should_stop=lambda: False,
    )
    first = worker.run_once()
    second = worker.run_once()
    assert first.registered_pick_ids == ("pick-1",)
    assert second.evaluation_ids == first.evaluation_ids
    assert repository.bookmakers == [8, 8]
    assert [request["bookmaker_id"] for request in quote_requests] == [8, 8]
    assert requests[0][1] == registration_request_id(requests[0][0])
    assert requests[2] == requests[0]


def test_opportunity_prediction_scope_failure_is_isolated_to_fixture() -> None:
    repository = OpportunityRepositoryFake()
    failures: list[tuple[str, str]] = []
    repository.record_item_failure = lambda _worker, item, error, **_kwargs: failures.append(
        (item, type(error).__name__)
    )
    worker = OpportunityWorker(
        repository,
        SimpleNamespace(fetch_quotes=lambda **_kwargs: ()),
        SimpleNamespace(ingest=lambda _quotes: 0),
        SimpleNamespace(
            execute=lambda _fixture_id: (_ for _ in ()).throw(
                DixonColesFitError("team absent from training sample")
            )
        ),
        SimpleNamespace(),
        SimpleNamespace(),
        scopes=(PilotScope(39, 2026),),
        bookmaker_id=8,
        provider_fixture_ids=frozenset(),
        allowed_statuses=("NS",),
        usable_scopes=lambda: frozenset({PilotScope(39, 2026)}),
        should_stop=lambda: False,
    )

    result = worker.run_once()

    assert result.failed_fixture_ids == ("api-football:123",)
    assert failures == [("api-football:123", "DixonColesFitError")]


class RuntimeFake:
    def __init__(self) -> None:
        self.started = self.succeeded = self.failed = 0

    def worker_started(self, *_args, **_kwargs):
        self.started += 1

    def worker_succeeded(self, *_args, **_kwargs):
        self.succeeded += 1

    def worker_failed(self, *_args, **_kwargs):
        self.failed += 1


def test_multicadence_scheduler_uses_interruptible_wait_without_busy_loop() -> None:
    stop = Event()
    runtime = RuntimeFake()

    def run():
        stop.set()

    result = ProductionOrchestrator(
        (ScheduledJob("one", 60, run),),
        runtime,
        instance_id="test",
        stop=stop,
        tick_seconds=5,
        leader_healthy=lambda: True,
    ).run_forever()
    assert result is True
    assert (runtime.started, runtime.succeeded, runtime.failed) == (1, 1, 0)


def test_health_http_exposes_liveness_and_structured_readiness() -> None:
    performance = SimpleNamespace(
        available_bankroll_minor=3_000_000, open_exposure_minor=0, currency="RSD"
    )
    runtime = SimpleNamespace(
        check_database=lambda: True,
        worker_statuses=lambda: (),
        operational_counts=lambda: {"retry": 0},
    )
    budget = SimpleNamespace(
        day=datetime.now(UTC).date(), used=1, effective_limit=6000, remaining=5999, exhausted=False
    )
    application = SimpleNamespace(
        runtime=runtime,
        budget=budget,
        provider_state=SimpleNamespace(
            last_error_class=None, last_error_message=None, last_error_at=None
        ),
        settings=SimpleNamespace(
            application=SimpleNamespace(
                registration_policy=SimpleNamespace(bankroll_account_id="pilot")
            )
        ),
        results=SimpleNamespace(performance=SimpleNamespace(summary=lambda _account: performance)),
    )
    state = RuntimeHealthState(
        schema_current=True, leadership="active", scheduler_alive=True, accepting_work=True
    )
    service = HealthService(application, state, host="127.0.0.1", port=0)
    service.start()
    try:
        with urlopen(f"http://127.0.0.1:{service.port}/livez") as response:
            assert json.load(response)["live"] is True
        with urlopen(f"http://127.0.0.1:{service.port}/readyz") as response:
            assert json.load(response)["ready"] is True
        old = datetime.now(UTC) - timedelta(minutes=10)
        runtime.worker_statuses = lambda: (
            WorkerStatus(
                "opportunity", old, old, None, old, 0, 1, 1, 0, None, None, "test", old
            ),
        )
        readiness = service.readiness()
        assert readiness["ready"] is False
        assert readiness["stale_workers"] == ["opportunity"]
    finally:
        service.close()


def test_railway_contract_uses_explicit_commands() -> None:
    root = Path(__file__).parents[1]
    railway = json.loads((root / "railway.json").read_text(encoding="utf-8"))
    assert railway["deploy"]["preDeployCommand"] == "python -m h2h.migrate"
    assert railway["deploy"]["startCommand"] == "python -m h2h.entrypoint"
    assert railway["deploy"]["healthcheckPath"] == "/livez"
    assert 'CMD ["python", "-m", "h2h.entrypoint"]' in (root / "Dockerfile").read_text()
