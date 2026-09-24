from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from urllib.request import urlopen

import pytest

from h2h.api.health import HealthService, RuntimeHealthState, WORKER_FRESHNESS_SECONDS
from h2h.config import ConfigError, load_production_settings
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.persistence.postgres_runtime import OpportunityFixture, OpportunitySelection, WorkerStatus
from h2h.quant import DixonColesFitError
from h2h.production import build_production_application
from h2h.workers.opportunity import OpportunityWorker
from h2h.workers.orchestrator import ProductionOrchestrator, ScheduledJob
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy

from tests.test_config import lifecycle_environment, registration_environment


STALE_RETRY_POLICY = StaleQuoteRetryPolicy(
    timedelta(minutes=2), timedelta(minutes=15), 5, timedelta(hours=1)
)


def production_environment() -> dict[str, str]:
    values = registration_environment()
    values.update(lifecycle_environment())
    values.update(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "INFO",
            "API_FOOTBALL_KEY": "test-key",
            "DATABASE_URL": "postgresql://example/quantbet",
            "QUANTBET_BOOKMAKER_ID": "8",
            "QUANTBET_BANKROLL_BOOTSTRAP_MODE": "verify",
        }
    )
    return values


def test_production_config_has_no_explicit_competition_scope() -> None:
    settings = load_production_settings(production_environment())
    assert settings.bookmaker_id == 8
    assert not hasattr(settings, "pilot_scopes")
    assert not hasattr(settings, "pilot_fixture_ids")
    assert settings.discovery_interval_seconds == 900
    assert settings.model_training_max_scopes == 1
    assert settings.model_training_max_provider_requests == 2
    assert settings.api_reserve == 0
    assert settings.model_training_daily_limit == 7500
    assert settings.model_training_operational_reserve == 0
    assert settings.model_training_policy.min_matches == 80
    assert settings.model_training_policy.xi == 0.0018
    assert settings.model_training_policy.previous_seasons == 1
    assert settings.api_football_published_max_age_seconds == 14400
    assert settings.live_close_poll_seconds == 60
    assert settings.live_close_window_seconds == 900
    assert settings.live_close_max_age_seconds == 120
    assert settings.stale_quote_retry_policy.initial_interval == timedelta(seconds=120)
    assert settings.stale_quote_retry_policy.max_interval == timedelta(seconds=900)
    assert settings.stale_quote_retry_policy.max_attempts == 5
    assert settings.stale_quote_retry_policy.horizon == timedelta(seconds=3600)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("QUANTBET_BOOKMAKER_ID", "7"),
        ("QUANTBET_BANKROLL_BOOTSTRAP_MODE", "automatic"),
        ("APP_ENV", "development"),
        ("LOG_LEVEL", "VERBOSE"),
        ("QUANTBET_MODEL_TRAINING_MAX_SCOPES", "0"),
        ("QUANTBET_MODEL_XI", "nan"),
        ("QUANTBET_STALE_QUOTE_INITIAL_RETRY_SECONDS", "0"),
        ("QUANTBET_STALE_QUOTE_MAX_ATTEMPTS", "0"),
        ("QUANTBET_LIVE_CLOSE_POLL_SECONDS", "0"),
        ("QUANTBET_LIVE_CLOSE_WINDOW_SECONDS", "0"),
        ("QUANTBET_LIVE_CLOSE_MAX_AGE_SECONDS", "0"),
        ("QUANTBET_API_FOOTBALL_PUBLISHED_MAX_AGE_SECONDS", "0"),
    ],
)
def test_production_config_rejects_partial_or_invalid_values(name: str, value: str) -> None:
    environment = production_environment()
    environment[name] = value
    with pytest.raises(ConfigError):
        load_production_settings(environment)


def test_production_config_rejects_provider_age_below_strict_quote_age() -> None:
    environment = production_environment()
    environment["QUANTBET_API_FOOTBALL_PUBLISHED_MAX_AGE_SECONDS"] = "299"

    with pytest.raises(ConfigError, match="must be at least"):
        load_production_settings(environment)


def test_production_config_rejects_inverted_stale_retry_bounds() -> None:
    environment = production_environment()
    environment["QUANTBET_STALE_QUOTE_INITIAL_RETRY_SECONDS"] = "600"
    environment["QUANTBET_STALE_QUOTE_MAX_RETRY_SECONDS"] = "300"

    with pytest.raises(ConfigError, match="stale quote max interval"):
        load_production_settings(environment)


def test_legacy_pilot_allowlists_do_not_define_production_universe() -> None:
    environment = production_environment()
    environment["QUANTBET_PILOT_SCOPES"] = "39:2026"
    environment["QUANTBET_PILOT_FIXTURE_IDS"] = "123"
    settings = load_production_settings(environment)
    assert settings.bookmaker_id == 8
    assert not hasattr(settings, "pilot_scopes")
    assert not hasattr(settings, "pilot_fixture_ids")


def test_production_composition_uses_categorized_clients_with_one_durable_budget() -> None:
    application = build_production_application(load_production_settings(production_environment()))
    assert application.opportunity._source.client is application.client
    assert application.client.transport.transport.budget is application.budget
    monitoring_client = application.monitoring.refresh_odds._source.client
    assert monitoring_client.odds_request_category == "results_monitoring"
    assert monitoring_client.transport.transport.budget is application.budget
    assert application.results.reconcile._source._client is monitoring_client
    assert application.live_closing_proxy._client is monitoring_client
    training_client = application.model_lifecycle._trainer._historical_results
    assert training_client._fetch_completed_fixtures.__self__.transport.transport.budget is (
        application.budget
    )
    durable = application.prediction.durable_discovery
    assert durable is not None
    provider_discovery = durable._discovery._discovery
    assert provider_discovery._client is application.client





def _btts_quotes(fixture_id: str, observed_at: datetime) -> tuple[CanonicalQuote, ...]:
    return (
        CanonicalQuote(
            fixture_id,
            8,
            "Bet365",
            Market.BTTS,
            Selection.YES,
            1.90,
            observed_at,
            "api-football",
        ),
        CanonicalQuote(
            fixture_id,
            8,
            "Bet365",
            Market.BTTS,
            Selection.NO,
            1.90,
            observed_at,
            "api-football",
        ),
    )


class OpportunityRepositoryFake:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.fixture = OpportunityFixture(
            "api-football:123",
            SimpleNamespace(fixture_id="api-football:123"),
            140,
            2026,
            now + timedelta(hours=2),
            None,
        )
        self.bookmakers: list[int] = []
        self.observed_at = now - timedelta(seconds=1)

    def select_opportunity_fixtures(self, **_kwargs):
        return OpportunitySelection(1, 0, 0, 0, (self.fixture,))

    def item_retry_due(self, *_args, **_kwargs):
        return True

    def latest_complete_snapshot_ids(self, _fixture_id, bookmaker_id):
        self.bookmakers.append(bookmaker_id)
        return ("snapshot-a", "snapshot-b")

    def latest_complete_market_states(self, _fixture_id, _bookmaker_id):
        return (
            SimpleNamespace(
                market="BTTS",
                observed_at=self.observed_at,
                captured_at=self.observed_at,
                source="api-football",
            ),
        )

    def record_quote_refresh_state(self, *_args, freshness_state, attempted_at, **_kwargs):
        return SimpleNamespace(
            freshness_state=freshness_state,
            stale_attempt_count=0,
            next_retry_at=None,
            last_attempt_at=attempted_at,
        )

    def record_item_failure(self, *_args, **_kwargs):
        raise AssertionError("unexpected item failure")

    def clear_item_failure(self, *_args, **_kwargs):
        return None


def test_opportunity_pipeline_is_deterministic_and_one_bookmaker_only() -> None:
    repository = OpportunityRepositoryFake()
    requests: list[tuple[str, str]] = []
    quote_requests: list[dict[str, object]] = []
    model_scopes: list[tuple[int, int]] = []

    def fetch_quotes(**kwargs):
        quote_requests.append(kwargs)
        return _btts_quotes(repository.fixture.fixture_id, repository.observed_at)

    source = SimpleNamespace(fetch_quotes=fetch_quotes)
    ingestion = SimpleNamespace(ingest=lambda _quotes: 0)
    predictor = SimpleNamespace(
        execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction-1")
    )
    evaluator = SimpleNamespace(
        execute=lambda _prediction, snapshot: SimpleNamespace(
            evaluation_id=f"eval-{snapshot}",
            bookmaker_id=8,
            market=SimpleNamespace(value="BTTS"),
            selected_selection=SimpleNamespace(value="YES"),
            selected_odd=1.5,
            edge=-0.1,
            expected_value=-0.1,
        )
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
        SimpleNamespace(
            execute=register,
            preliminary_rejection_codes=lambda _evaluation_id: ("EDGE_BELOW_MINIMUM",),
        ),
        bookmaker_id=8,
        allowed_statuses=("NS",),
        ensure_model_available=lambda fixture: model_scopes.append(
            (fixture.league_id, fixture.season)
        ),
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=STALE_RETRY_POLICY,
    )
    first = worker.run_once()
    second = worker.run_once()
    assert first.registered_pick_ids == ()
    assert first.quotes_fetched == 1
    assert first.fresh_quotes == 0
    assert first.decisions == 0
    assert second.evaluation_ids == first.evaluation_ids
    assert repository.bookmakers == [8, 8]
    assert [request["bookmaker_id"] for request in quote_requests] == [8, 8]
    assert model_scopes == [(140, 2026), (140, 2026)]
    assert requests == []


def test_due_non_epl_fixture_without_model_is_explicit_and_stops_before_odds() -> None:
    repository = OpportunityRepositoryFake()
    quote_requests: list[object] = []
    failures: list[tuple[str, str]] = []
    repository.record_item_failure = lambda _worker, item, error, **_kwargs: failures.append(
        (item, type(error).__name__)
    )

    def unavailable(_fixture):
        raise ActiveModelUnavailableError("no active model exists for the requested scope")

    worker = OpportunityWorker(
        repository,
        SimpleNamespace(fetch_quotes=lambda **kwargs: quote_requests.append(kwargs)),
        SimpleNamespace(ingest=lambda _quotes: 0),
        SimpleNamespace(execute=lambda _fixture_id: pytest.fail("prediction must not run")),
        SimpleNamespace(),
        SimpleNamespace(),
        bookmaker_id=8,
        allowed_statuses=("NS",),
        ensure_model_available=unavailable,
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=STALE_RETRY_POLICY,
    )

    result = worker.run_once()

    assert result.due_fixture_ids == ("api-football:123",)
    assert result.model_unavailable_fixture_ids == ("api-football:123",)
    assert result.prediction_ids == ()
    assert result.registered_pick_ids == ()
    assert quote_requests == []
    assert failures == [("api-football:123", "ActiveModelUnavailableError")]


def test_opportunity_prediction_scope_failure_is_isolated_to_fixture() -> None:
    repository = OpportunityRepositoryFake()
    failures: list[tuple[str, str]] = []
    repository.record_item_failure = lambda _worker, item, error, **_kwargs: failures.append(
        (item, type(error).__name__)
    )
    worker = OpportunityWorker(
        repository,
        SimpleNamespace(
            fetch_quotes=lambda **_kwargs: _btts_quotes(
                repository.fixture.fixture_id, repository.observed_at
            )
        ),
        SimpleNamespace(ingest=lambda _quotes: 0),
        SimpleNamespace(
            execute=lambda _fixture_id: (_ for _ in ()).throw(
                DixonColesFitError("team absent from training sample")
            )
        ),
        SimpleNamespace(),
        SimpleNamespace(),
        bookmaker_id=8,
        allowed_statuses=("NS",),
        ensure_model_available=lambda _fixture: None,
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=STALE_RETRY_POLICY,
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
    assert WORKER_FRESHNESS_SECONDS == 120
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
        results=SimpleNamespace(
            performance=SimpleNamespace(
                summary=lambda _account: performance,
                operator_summary=lambda _account: performance,
            )
        ),
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
            WorkerStatus("opportunity", old, old, None, old, 0, 1, 1, 0, None, None, "test", old),
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
