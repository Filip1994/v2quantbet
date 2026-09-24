from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
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
        "last_observed_odd": 2.01,
        "last_observed_at": NOW,
        "last_checked_at": NOW - timedelta(minutes=7),
        "last_observed_source": "SAME_BOOK",
        "last_observed_freshness": "FRESH",
        "display_closing_odd": 2.05,
        "display_closing_observed_at": NOW,
        "display_closing_source": "SAME_BOOK",
        "bookmaker_key": "bet365",
        "source": "api-football",
        "first_seen_observed_at": NOW,
        "pick_observed_at": NOW,
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
        "manual_clv_ppm": None,
        "proxy_clv_ppm": None,
        "dashboard_phase": "SETTLED",
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
            "open_exposure_minor": 300_000,
            "max_open_exposure_minor": 300_000,
            "fixed_stake_minor": 30_000,
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


def test_settled_pick_moves_to_compact_history_with_clear_positive_clv() -> None:
    html = RenderingDashboard(_snapshot([_pick()])).render_html()

    assert "<h2>Active picks</h2>" in html
    assert "No active picks." in html
    assert "<h2>History</h2>" in html
    assert "1 finished" in html
    assert "Open exposure / cap" in html
    assert "3,000.00 RSD / 3,000.00 RSD" in html
    assert "1.95 → 2.05" in html
    assert '<th class="num">Probability</th>' in html
    assert 'class="num history-probability"' in html
    assert "<strong>Model 58.00%</strong>" in html
    assert "<small>Market fair 51.00%</small>" in html
    assert 'class="num history-clv good"' in html
    assert "<strong>+5.00%</strong>" in html
    assert "GOOD · SAME-BOOK" in html
    assert '<span class="status win">WIN</span>' in html
    assert "950.00 RSD" in html
    assert "Red &amp; &lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "Best current" not in html
    assert "Same-book close" not in html
    assert "Market close" not in html


def test_registered_bookmaker_identity_is_kept_on_active_pick() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    dashboard_phase="PREMATCH",
                    settlement_outcome=None,
                    settled_at=None,
                    last_observed_at=NOW - timedelta(hours=2, minutes=36),
                )
            ]
        )
    ).render_html()

    assert html.count('data-bookmaker="bet365"') == 1
    assert 'class="pick-book"' in html
    assert "best at" not in html


def test_active_odds_lifecycle_has_only_four_checkpoints() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    dashboard_phase="PREMATCH",
                    settlement_outcome=None,
                    settled_at=None,
                )
            ]
        )
    ).render_html()

    for label in ("First seen", "Pick", "Last observed", "Closing"):
        assert f"<b>{label}</b>" in html
    assert '<small class="quote-age">2h 36mins ago</small>' in html
    assert '<small class="check-age">checked 7min ago</small>' in html
    assert 'title="23 Sep 2026 · 09:24 UTC"' in html
    assert "Observed 23 Sep" not in html
    assert "Best current" not in html
    assert "Same-book current" not in html
    assert "Market close" not in html


def test_prematch_stale_quality_is_still_visible_before_kickoff() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    dashboard_phase="PREMATCH",
                    settlement_outcome=None,
                    settled_at=None,
                    last_observed_freshness="STALE",
                    warning_codes=["STALE_QUOTE_WARNING"],
                    stale_quote=True,
                )
            ]
        )
    ).render_html()

    assert "<b>Last observed</b>2.01" in html
    assert '<span class="quality-badge stale" title="Latest pre-match observation is stale">STALE</span>' in html
    assert ">Entry stale</small>" in html
    assert "STALE NOW" not in html


def test_live_pick_stays_active_and_uses_live_quality() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    dashboard_phase="LIVE",
                    settlement_outcome=None,
                    settled_at=None,
                    last_observed_freshness="STALE",
                    display_closing_source="SAME_BOOK",
                )
            ]
        )
    ).render_html()

    assert "<h2>Active picks</h2>" in html
    assert ">LIVE</span>" in html
    assert 'quality-badge stale' not in html


@pytest.mark.parametrize("phase", ["FINISHED", "CLOSED", "SETTLED"])
def test_finished_closed_and_settled_picks_move_to_history(phase: str) -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    dashboard_phase=phase,
                    settlement_outcome="WIN" if phase == "SETTLED" else None,
                    settled_at=NOW if phase == "SETTLED" else None,
                )
            ]
        )
    ).render_html()

    assert "No active picks." in html
    assert "<h2>History</h2>" in html
    if phase == "SETTLED":
        assert '<span class="status win">WIN</span>' in html
    else:
        assert f">{phase}</span>" in html


def test_prematch_unavailable_is_distinct_from_post_kickoff_state() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    dashboard_phase="PREMATCH",
                    settlement_outcome=None,
                    settled_at=None,
                    last_observed_odd=None,
                    last_observed_at=None,
                    last_observed_source="UNAVAILABLE",
                    last_observed_freshness="UNAVAILABLE",
                    warning_codes=[],
                    stale_quote=False,
                )
            ]
        )
    ).render_html()

    assert ">UNAVAILABLE</span>" in html
    assert "<b>Last observed</b>—" in html


def test_live_proxy_is_folded_into_last_observed_and_closing() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    clv_ppm=None,
                    dashboard_phase="LIVE",
                    settlement_outcome=None,
                    settled_at=None,
                    last_observed_odd=1.88,
                    last_observed_source="LIVE_PROXY",
                    display_closing_odd=1.88,
                    display_closing_source="LIVE_PROXY",
                    proxy_clv_ppm=37_234,
                )
            ]
        )
    ).render_html()

    assert "<b>Last observed</b>1.88" in html
    assert "<b>Closing</b>1.88" in html
    assert html.count("LIVE PROXY") >= 2
    assert "Proxy CLV +3.72%" in html
    assert "Market close" not in html


def test_manual_close_in_history_shows_bad_clv_and_true_clv_still_wins() -> None:
    manual = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    clv_ppm=None,
                    display_closing_odd=2.01,
                    display_closing_source="MANUAL",
                    manual_clv_ppm=-29_851,
                )
            ]
        )
    ).render_html()
    true_clv = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    clv_ppm=50_000,
                    display_closing_odd=2.01,
                    display_closing_source="MANUAL",
                    manual_clv_ppm=-29_851,
                )
            ]
        )
    ).render_html()

    assert "1.95 → 2.01" in manual
    assert "Pick → Closing · manual" in manual
    assert "Last observed · 23 Sep 2026 · 12:00 UTC" in manual
    assert 'class="num history-clv bad"' in manual
    assert "<strong>-2.99%</strong>" in manual
    assert "BAD · MANUAL" in manual

    assert 'class="num history-clv good"' in true_clv
    assert "<strong>+5.00%</strong>" in true_clv
    assert "GOOD · SAME-BOOK" in true_clv
    assert "BAD · MANUAL" not in true_clv


def test_loss_is_red_in_history_and_operator_toggle_remains_available() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    operator_state="SKIPPED",
                    settlement_outcome="LOSS",
                    realized_pnl_minor=-100_000,
                )
            ]
        )
    ).render_html()

    assert '<span class="status loss">LOSS</span>' in html
    assert "SKIPPED" in html
    assert 'value="PLAYED"' in html
    assert "-1 000.00 RSD" in html


def test_history_probability_handles_missing_values_explicitly() -> None:
    html = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    model_probability=None,
                    devig_probability=None,
                )
            ]
        )
    ).render_html()

    assert "<strong>Model —</strong>" in html
    assert "<small>Market fair —</small>" in html


def test_render_empty_and_missing_durable_values_as_explicit_unavailable() -> None:
    empty = RenderingDashboard(_snapshot([])).render_html()
    missing = RenderingDashboard(
        _snapshot(
            [
                _pick(
                    first_seen_odd=None,
                    last_observed_odd=None,
                    last_observed_at=None,
                    last_observed_source="UNAVAILABLE",
                    last_observed_freshness="UNAVAILABLE",
                    display_closing_odd=None,
                    display_closing_observed_at=None,
                    display_closing_source="UNAVAILABLE",
                    dashboard_phase="PREMATCH",
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

    assert "No active picks." in empty
    assert "No finished picks yet." in empty
    assert "MONITORING" in missing
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
