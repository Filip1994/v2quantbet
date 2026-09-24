from __future__ import annotations

import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

import pytest

from h2h.api.dashboard import DashboardHTTPService, DashboardService
from h2h import entrypoint


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _pick(**changes: object) -> dict[str, object]:
    pick: dict[str, object] = {
        "pick_id": "registered-pick-v1:0123456789abcdef",
        "home_team": "Red & <script>alert(1)</script>",
        "away_team": "Blue",
        "competition_name": "Premier <League>",
        "kickoff_at": NOW,
        "market": "OU_25",
        "selection": "OVER",
        "first_seen_odd": 1.91,
        "pick_odd": 1.95,
        "current_odd": 2.01,
        "current_freshness": "FRESH",
        "current_quote_age_seconds": 30,
        "current_max_age_seconds": 300,
        "best_current_odd": 2.10,
        "best_current_bookmaker_key": "superbet",
        "best_current_observed_at": NOW,
        "closing_odd": 2.05,
        "bookmaker_key": "bet365",
        "source": "api-football",
        "first_seen_observed_at": NOW,
        "pick_observed_at": NOW,
        "current_observed_at": NOW,
        "closing_observed_at": NOW,
        "model_probability": 0.58,
        "implied_probability": 0.5236,
        "devig_probability": 0.51,
        "edge": 0.07,
        "expected_value": 0.131,
        "stake_minor": 100_000,
        "realized_pnl_minor": 95_000,
        "settlement_outcome": "WIN",
        "settled_at": NOW,
        "clv_ppm": 50_000,
        "warning_codes": ["SOURCE_<STALE>"],
        "stale_quote": True,
        "closing_status": "CAPTURED",
        "model_version_id": "dc-v7",
        "config_fingerprint": "pick-policy-config-v1:abc",
        "prediction_method_version": "DIXON_COLES_V1",
        "eligibility_policy_version": "ELIGIBILITY_V1",
        "risk_policy_version": "RISK_V1",
        "staking_policy_version": "FIXED_STAKE_V1",
        "operator_state": "PLAYED",
    }
    pick.update(changes)
    return pick


def _snapshot(picks: list[dict[str, object]]) -> dict[str, object]:
    return {
        "generated_at": NOW,
        "bankroll": {
            "initial_minor": 3_000_000,
            "available_minor": 3_095_000,
            "open_exposure_minor": 0,
            "total_staked_minor": 100_000,
            "settled_stake_minor": 100_000,
            "gross_returns_minor": 195_000,
            "realized_pnl_minor": 95_000,
            "pending_minor": 0,
            "currency": "RSD",
        },
        "counts": {
            "all": len(picks),
            "played": len(picks),
            "skipped": 0,
            "active": 0,
            "won": 1,
            "lost": 0,
            "void": 0,
        },
        "provider_budget": {
            "used": 32,
            "remaining": 7468,
            "effective_limit": 7500,
            "by_category": {"discovery": 32},
        },
        "operations": {
            "database_reachable": True,
            "workers": [],
            "last_engine_refresh": NOW,
            "last_discovery": NOW,
            "last_odds_ingestion": NOW,
            "recent_failures": 0,
            "stale_workers": [],
            "counts": {},
        },
        "picks": picks,
    }


class RenderingDashboard(DashboardService):
    def __init__(self, snapshot: dict[str, object]) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> dict[str, object]:
        return self._snapshot


def test_render_populated_history_preserves_odds_settlement_clv_and_escapes_html() -> None:
    html = RenderingDashboard(_snapshot([_pick()])).render_html()

    assert "1.91" in html
    assert "1.95" in html
    assert "2.01" in html
    assert "2.10" in html
    assert "2.05" in html
    assert "950.00 RSD" in html
    assert "+5.00%" in html
    assert "SOURCE_&lt;STALE&gt;" in html
    assert ">FRESH</span>" in html
    assert "Entry stale" in html
    assert "Entry warning" in html
    assert "Red &amp; &lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "FIXED_STAKE_V1" in html
    assert "Best current" in html
    assert "superbet" in html
    assert 'aria-label="Same-bookmaker price moved up"' in html
    assert "<th>Provenance</th>" not in html
    assert "Plain-language glossary" in html
    assert "PLAYED" in html
    assert 'value="SKIPPED"' in html


def test_bookmaker_identity_is_shown_once_per_pick_and_best_book_only_when_different() -> None:
    same_book = RenderingDashboard(
        _snapshot([_pick(best_current_bookmaker_key="bet365")])
    ).render_html()
    different_book = RenderingDashboard(_snapshot([_pick()])).render_html()

    assert same_book.count('data-bookmaker="bet365"') == 1
    assert 'class="best-book-switch"' not in same_book
    assert 'class="pick-book"' in same_book

    assert different_book.count('data-bookmaker="bet365"') == 1
    assert different_book.count('data-bookmaker="superbet"') == 1
    assert 'class="best-book-switch"' in different_book
    assert "best at" in different_book


def test_same_bookmaker_movement_is_accessible_for_down_and_neutral() -> None:
    down = RenderingDashboard(_snapshot([_pick(current_odd=1.80)])).render_html()
    neutral = RenderingDashboard(_snapshot([_pick(current_odd=1.95)])).render_html()

    assert 'class="movement down"' in down
    assert 'aria-label="Same-bookmaker price moved down"' in down
    assert 'class="movement neutral"' in neutral
    assert 'aria-label="Same-bookmaker price unchanged"' in neutral


def test_stale_current_is_labeled_as_last_observed_and_not_as_live_movement() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    current_freshness="STALE",
                    current_quote_age_seconds=3900,
                    best_current_odd=None,
                    best_current_bookmaker_key=None,
                    best_current_observed_at=None,
                    warning_codes=["STALE_QUOTE_WARNING"],
                    stale_quote=True,
                )
            ]
        )
    ).render_html()

    assert "<b>Last observed</b>" in html
    assert "STALE · 1h 05m old" in html
    assert '<span class="quality-badge stale" title="Latest registered-book provider observation is too old">STALE NOW</span>' in html
    assert '<small class="quality-history"' in html
    assert ">Entry stale</small>" in html
    assert 'aria-label="Same-bookmaker price moved up"' not in html
    assert "STALE_QUOTE_WARNING" not in html


def test_quality_consolidates_live_and_historical_stale_states() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    current_freshness="STALE",
                    warning_codes=["STALE_QUOTE_WARNING"],
                    stale_quote=True,
                    closing_status="STALE_QUOTE",
                )
            ]
        )
    ).render_html()

    assert '<span class="quality-badge stale" title="Latest registered-book provider observation is too old">STALE NOW</span>' in html
    assert ">Entry stale · Closing stale</small>" in html
    assert "CURRENT STALE" not in html
    assert "ENTRY STALE" not in html
    assert "CLOSING STALE" not in html


def test_current_unavailable_is_distinct_from_historical_entry_warning() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    current_odd=None,
                    current_observed_at=None,
                    current_freshness="UNAVAILABLE",
                    current_quote_age_seconds=None,
                    warning_codes=[],
                    stale_quote=False,
                )
            ]
        )
    ).render_html()

    assert ">UNAVAILABLE</span>" in html
    assert '<small class="quote-age unavailable">UNAVAILABLE</small>' in html
    assert "ENTRY STALE" not in html


def test_dashboard_renders_skipped_operator_state_without_hiding_system_pick() -> None:
    html = RenderingDashboard(
        _snapshot([_pick(operator_state="SKIPPED", settlement_outcome="LOSS")])
    ).render_html()

    assert "SKIPPED" in html
    assert "LOSS" in html
    assert 'value="PLAYED"' in html


def test_render_empty_and_missing_durable_values_as_explicit_unavailable() -> None:
    empty = RenderingDashboard(_snapshot([])).render_html()
    missing = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    first_seen_odd=None,
                    current_odd=None,
                    current_observed_at=None,
                    current_freshness="UNAVAILABLE",
                    current_quote_age_seconds=None,
                    closing_odd=None,
                    realized_pnl_minor=None,
                    settlement_outcome=None,
                    settled_at=None,
                    clv_ppm=None,
                    warning_codes=[],
                    stale_quote=False,
                    monitoring_state="MONITORING",
                )
            ]
        )
    ).render_html()

    assert "No registered picks yet." in empty
    assert "MONITORING" in missing
    assert "None" in missing
    assert "—" in missing


def test_snapshot_uses_performance_facts_for_financial_summary() -> None:
    performance = SimpleNamespace(
        initial_bankroll_minor=3_000_000,
        available_bankroll_minor=3_095_000,
        open_exposure_minor=50_000,
        resolved_stake_minor=100_000,
        realized_pnl_minor=95_000,
        pending_stake_minor=50_000,
        currency="RSD",
        pending_count=1,
        win_count=1,
        loss_count=0,
        void_count=0,
        total_staked_minor=100_000,
        gross_returns_minor=195_000,
    )
    application = SimpleNamespace(
        settings=SimpleNamespace(
            application=SimpleNamespace(
                registration_policy=SimpleNamespace(
                    bankroll_account_id="pilot", initial_bankroll_minor=3_000_000
                )
            )
        ),
        results=SimpleNamespace(
            performance=SimpleNamespace(
                summary=lambda _account: performance,
                operator_summary=lambda _account: performance,
            )
        ),
        budget=SimpleNamespace(
            usage_by_category=lambda: {"discovery": 10, "results_monitoring": 5},
            effective_limit=7500,
        ),
    )

    class Projection(DashboardService):
        def _picks(self) -> list[dict[str, object]]:
            return [
                {
                    "stake_minor": 100_000,
                    "gross_return_minor": 195_000,
                    "settlement_outcome": "WIN",
                    "operator_state": "PLAYED",
                },
                {
                    "stake_minor": 50_000,
                    "gross_return_minor": None,
                    "settlement_outcome": None,
                    "operator_state": "SKIPPED",
                },
            ]

        def _operations(self, _generated_at: datetime) -> dict[str, object]:
            return {"database_reachable": True}

    data = Projection(application).snapshot()

    assert data["bankroll"]["total_staked_minor"] == 100_000
    assert data["bankroll"]["settled_stake_minor"] == 100_000
    assert data["bankroll"]["gross_returns_minor"] == 195_000
    assert data["bankroll"]["realized_pnl_minor"] == 95_000
    assert data["provider_budget"]["remaining"] == 7485


@pytest.fixture
def dashboard_server(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QUANTBET_DASHBOARD_USER", "operator")
    monkeypatch.setenv("QUANTBET_DASHBOARD_PASSWORD", "correct horse")
    service = DashboardHTTPService(RenderingDashboard(_snapshot([])), host="127.0.0.1", port=0)
    service.start()
    try:
        yield service
    finally:
        service.close()


def test_dashboard_http_auth_security_headers_and_no_write_path(dashboard_server) -> None:
    url = f"http://127.0.0.1:{dashboard_server.port}/"
    with pytest.raises(HTTPError) as unauthorized:
        urlopen(url)
    assert unauthorized.value.code == 401
    assert unauthorized.value.headers["WWW-Authenticate"]

    token = base64.b64encode(b"operator:correct horse").decode()
    request = Request(url, headers={"Authorization": f"Basic {token}"})
    with urlopen(request) as response:
        assert response.status == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Content-Security-Policy"]

    with pytest.raises(HTTPError) as post_response:
        urlopen(Request(url, method="POST", data=b""))
    assert post_response.value.code == 404


def test_operator_write_is_authenticated_even_when_dashboard_is_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class WritableDashboard(RenderingDashboard):
        def set_operator_state(self, pick_id, state, request_id):
            calls.append((pick_id, state, request_id))
            return {"pick_id": pick_id, "state": state, "request_id": request_id}

    monkeypatch.setenv("QUANTBET_DASHBOARD_PUBLIC", "true")
    monkeypatch.setenv("QUANTBET_DASHBOARD_USER", "operator")
    monkeypatch.setenv("QUANTBET_DASHBOARD_PASSWORD", "correct horse")
    service = DashboardHTTPService(
        WritableDashboard(_snapshot([_pick()])), host="127.0.0.1", port=0
    )
    service.start()
    path = "/api/picks/registered-pick-v1%3A0123456789abcdef/operator-state"
    data = urlencode({"state": "SKIPPED", "request_id": "request-1"}).encode()
    try:
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(Request(f"http://127.0.0.1:{service.port}{path}", data=data))
        assert unauthorized.value.code == 401
        token = base64.b64encode(b"operator:correct horse").decode()
        request = Request(
            f"http://127.0.0.1:{service.port}{path}",
            data=data,
            headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
        )
        with urlopen(request) as response:
            assert response.status == 200
        assert calls == [("registered-pick-v1:0123456789abcdef", "SKIPPED", "request-1")]
    finally:
        service.close()


def test_operator_write_response_serializes_timestamp() -> None:
    event = SimpleNamespace(
        event_id="event-1",
        pick_id="registered-pick-v1:0123456789abcdef",
        state=SimpleNamespace(value="SKIPPED"),
        occurred_at=NOW,
        request_id="request-1",
    )
    application = SimpleNamespace(
        operator_picks=SimpleNamespace(set_state=lambda *_args, **_kwargs: event)
    )

    result = DashboardService(application).set_operator_state(
        event.pick_id, "SKIPPED", event.request_id
    )

    assert result["occurred_at"] == "2026-09-23T12:00:00+00:00"


def test_dashboard_fails_closed_without_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTBET_DASHBOARD_PASSWORD", raising=False)
    service = DashboardHTTPService(RenderingDashboard(_snapshot([])), host="127.0.0.1", port=0)
    service.start()
    try:
        with pytest.raises(HTTPError) as response:
            urlopen(f"http://127.0.0.1:{service.port}/dashboard")
        assert response.value.code == 404
    finally:
        service.close()


def test_dashboard_public_mode_needs_no_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTBET_DASHBOARD_PUBLIC", "true")
    monkeypatch.delenv("QUANTBET_DASHBOARD_USER", raising=False)
    monkeypatch.delenv("QUANTBET_DASHBOARD_PASSWORD", raising=False)
    service = DashboardHTTPService(RenderingDashboard(_snapshot([])), host="127.0.0.1", port=0)
    service.start()
    try:
        with urlopen(f"http://127.0.0.1:{service.port}/") as response:
            assert response.status == 200
            assert b"QuantBet" in response.read()
    finally:
        service.close()


def test_root_entrypoint_dispatches_dashboard_without_composing_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("QUANTBET_PROCESS", "dashboard")
    monkeypatch.setattr("h2h.dashboard_entrypoint.main", lambda: calls.append("dashboard"))
    monkeypatch.setattr(
        entrypoint,
        "load_production_settings",
        lambda: pytest.fail("worker settings must not load for the dashboard process"),
    )

    entrypoint.main()

    assert calls == ["dashboard"]
