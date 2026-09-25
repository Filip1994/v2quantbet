from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from h2h.api.health import RuntimeHealthState
from h2h.dashboard_entrypoint import build_dashboard_application
from h2h.domain.fixture_identity import api_football_fixture_identity
from h2h.entrypoint import _fixture_identities_from_environment, _run_active_leader
from h2h.persistence.operator_pick_state import PostgreSQLOperatorPickStateRepository
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy


def test_manual_fixture_allowlist_resolves_api_football_canonical_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTBET_FIXTURE_IDS", "123, 456")

    assert _fixture_identities_from_environment() == (
        api_football_fixture_identity(123),
        api_football_fixture_identity(456),
    )


def test_standalone_dashboard_composes_operator_state_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/quantbet")
    monkeypatch.setenv("QUANTBET_BANKROLL_ACCOUNT_ID", "bankroll")

    application = build_dashboard_application()

    assert isinstance(
        application.operator_picks, PostgreSQLOperatorPickStateRepository
    )


@pytest.mark.parametrize("value", ["0", "-1", "raw-id"])
def test_manual_fixture_allowlist_rejects_invalid_provider_ids(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("QUANTBET_FIXTURE_IDS", value)

    with pytest.raises(ValueError, match="positive integers|contain integers"):
        _fixture_identities_from_environment()


def test_active_leader_preflight_passes_freshness_scheduling_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    retry_policy = StaleQuoteRetryPolicy(
        timedelta(minutes=2), timedelta(minutes=15), 5, timedelta(hours=1)
    )
    registration_policy = SimpleNamespace(
        bankroll_account_id="bankroll",
        currency="RSD",
        initial_bankroll_minor=3_000_000,
        allowed_fixture_statuses=("NS",),
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
    )
    application = SimpleNamespace(
        settings=SimpleNamespace(
            bookmaker_id=8,
            bankroll_bootstrap_mode="verify",
            stale_quote_retry_policy=retry_policy,
            discovery_interval_seconds=900,
            discovery_lookahead_hours=72,
            model_training_interval_seconds=60,
            opportunity_interval_seconds=60,
            live_close_poll_seconds=60,
            scheduler_tick_seconds=5,
            application=SimpleNamespace(
                registration_policy=registration_policy,
                odds_lifecycle_policy=SimpleNamespace(monitoring_interval_seconds=300),
                result_settlement_policy=SimpleNamespace(poll_interval_seconds=300),
                bulletin_timezone=ZoneInfo("Europe/Belgrade"),
            ),
        ),
        runtime=SimpleNamespace(
            verify_bankroll=lambda *_args: None,
            due_opportunity_fixtures=lambda **kwargs: calls.append(kwargs),
        ),
        registration=SimpleNamespace(
            bootstrap_bankroll=SimpleNamespace(execute=lambda: None),
            repository=SimpleNamespace(risk_exposure_breakdown=lambda *_args, **_kwargs: {}),
        ),
        monitoring=SimpleNamespace(
            reconcile=SimpleNamespace(execute=lambda: None),
            worker=SimpleNamespace(run_once=lambda: None, has_pending=False),
            bulletin=SimpleNamespace(generate=lambda *_args, **_kwargs: None),
        ),
        research=SimpleNamespace(
            reconcile=SimpleNamespace(execute=lambda: None),
            worker=SimpleNamespace(run_once=lambda: None, has_pending=False),
        ),
        results=SimpleNamespace(
            repository=SimpleNamespace(reconcile=lambda **_kwargs: None),
            worker=SimpleNamespace(run_once=lambda: None, has_pending=False),
        ),
        prediction=SimpleNamespace(
            durable_discovery=SimpleNamespace(has_pending=False, discover=lambda *_args: ())
        ),
        model_lifecycle=SimpleNamespace(run_once=lambda: None, has_pending=False),
        opportunity=SimpleNamespace(run_once=lambda: None, has_pending=False),
        live_closing_proxy=SimpleNamespace(run_once=lambda: None),
    )
    monkeypatch.setattr(
        "h2h.entrypoint.ProductionOrchestrator",
        lambda *_args, **_kwargs: SimpleNamespace(run_forever=lambda: True),
    )

    assert (
        _run_active_leader(
            application,
            RuntimeHealthState(),
            Event(),
            SimpleNamespace(healthy=lambda: True),
            "instance",
        )
        is True
    )
    assert len(calls) == 1
    assert calls[0]["maximum_quote_age_seconds"] == 300
    assert calls[0]["minimum_time_to_kickoff_seconds"] == 600
    assert calls[0]["stale_retry_policy"] is retry_policy
