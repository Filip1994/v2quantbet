"""Bounded Production-only manual corner settlement tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from h2h.api.dashboard import DashboardHTTPService, DashboardService
from h2h.manual_corner_settlement import (
    ManualSettlementBusy,
    _needs_statistics,
    run_manual_corner_settlement,
)


NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


class _LockCursor:
    def __init__(self, *, acquired: bool = True):
        self.acquired = acquired

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        assert "advisory_lock" in query

    def fetchone(self):
        return (self.acquired,)


class _LockConnection:
    def __init__(self, *, acquired=True):
        self.acquired = acquired
        self.closed = False

    def cursor(self):
        return _LockCursor(acquired=self.acquired)

    def close(self):
        self.closed = True


class _Repo:
    def __init__(self):
        self.saved = []

    def corner_shadow_settlement_candidates(self, *, limit, production_only):
        assert production_only is True
        assert limit == 5000
        return ({
            "shadow_bet_id": "quantlab-shadow-v1:" + "a" * 64,
            "fixture_id": "api-football:123",
            "market_key": "TOTAL_CORNERS",
            "selection": "OVER",
            "line": Decimal("8.5"),
            "odds": Decimal("1.90"),
            "stake_minor": 1000,
            "result_observation_id": "result:123",
            "result_classification": "PLAYED_SETTLEABLE",
            "provider_status": "FT",
            "statistics_observation_id": "stats:123",
            "statistics_available_at": NOW - timedelta(minutes=45),
            "home_corner_kicks": 5,
            "away_corner_kicks": 4,
        },)

    def save_corner_settlement_event(self, event):
        self.saved.append(event)
        return True


def _run(monkeypatch, *, candidate_rows=(), acquired=True):
    from h2h import manual_corner_settlement as module

    conn = _LockConnection(acquired=acquired)
    repo = _Repo()
    monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: conn)
    monkeypatch.setattr(module, "PostgreSQLQuantLabRepository", lambda *args: repo)
    monkeypatch.setattr(module, "_pending_production_corners", lambda repository, now: candidate_rows)
    monkeypatch.setattr(module, "QuantLabRequestBudget", lambda **kwargs: SimpleNamespace(used=0))
    monkeypatch.setattr(module, "QuantLabApiFootballClient", lambda **kwargs: None)
    result = run_manual_corner_settlement(
        database_url="postgresql://fake/test",
        api_key="test-only",
        daily_limit=7500,
        reserve=0,
        now=NOW,
    )
    assert conn.closed
    return result, repo


def test_no_pending_production_corners_makes_zero_api_calls(monkeypatch):
    result, repo = _run(monkeypatch)
    assert result["fixtures_checked"] == 0
    assert result["settled_picks"] == 0
    assert result["api_calls"] == 0
    assert repo.saved == []


def test_existing_terminal_result_and_post_final_stats_are_settled(monkeypatch):
    row = {
        "fixture_id": "api-football:123",
        "provider_fixture_id": 123,
        "kickoff_at": NOW - timedelta(hours=3),
        "provider_status": "FT",
        "result_captured_at": NOW - timedelta(hours=1),
        "statistics_at": NOW - timedelta(minutes=45),
        "last_statistics_capture_at": NOW - timedelta(minutes=45),
        "home_team_id": 1,
        "away_team_id": 2,
    }
    result, repo = _run(monkeypatch, candidate_rows=(row,))
    assert result["fixtures_checked"] == 1
    assert result["settled_picks"] == 1
    assert result["api_calls"] == 0
    assert repo.saved[0].outcome == "WIN"


def test_old_live_stats_require_final_refresh():
    assert _needs_statistics(
        {"statistics_at": NOW - timedelta(hours=2)},
        terminal_at=NOW - timedelta(hours=1),
    )
    assert not _needs_statistics(
        {"statistics_at": NOW - timedelta(minutes=45)},
        terminal_at=NOW - timedelta(hours=1),
    )


def test_manual_run_respects_collector_exclusive_lock(monkeypatch):
    from h2h import manual_corner_settlement as module

    conn = _LockConnection(acquired=False)
    monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: conn)
    with pytest.raises(ManualSettlementBusy):
        module.run_manual_corner_settlement(
            database_url="postgresql://fake/test",
            api_key="test-only",
            daily_limit=7500,
            reserve=0,
        )
    assert conn.closed


def test_public_manual_route_is_post_only_and_rejects_cross_origin(monkeypatch):
    monkeypatch.setenv("QUANTBET_DASHBOARD_PUBLIC", "true")
    class Dashboard(DashboardService):
        def __init__(self):
            super().__init__(SimpleNamespace())
            self.calls = 0

        def trigger_manual_settlement(self):
            self.calls += 1
            return {"state": "running"}

    dashboard = Dashboard()
    server = DashboardHTTPService(dashboard, host="127.0.0.1", port=0)
    server.start()
    url = f"http://127.0.0.1:{server.port}/api/settlement/run"
    try:
        with pytest.raises(HTTPError) as unsupported_get:
            urlopen(url)
        assert unsupported_get.value.code == 404
        with pytest.raises(HTTPError) as cross_site:
            urlopen(Request(url, data=b"", headers={"Origin": "https://evil.example"}))
        assert cross_site.value.code == 403
        assert dashboard.calls == 0
        with urlopen(Request(url, data=b"", headers={"Accept": "application/json"})) as response:
            assert response.status == 202
            assert b"running" in response.read()
        assert dashboard.calls == 1
    finally:
        server.close()
