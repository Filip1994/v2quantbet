from __future__ import annotations

from threading import Event

import pytest

import h2h.quantlab_dashboard_entrypoint as entrypoint


class _Repository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def check_database(self) -> bool:
        return True


class _Dashboard:
    def __init__(self, repository: _Repository, *, api_daily_limit: int, currency: str) -> None:
        self.repository = repository
        self.api_daily_limit = api_daily_limit
        self.currency = currency


class _Server:
    started = False
    closed = False

    def __init__(self, dashboard: _Dashboard, *, host: str, port: int) -> None:
        self.dashboard = dashboard
        self.host = host
        self.port = port

    def start(self) -> None:
        type(self).started = True

    def close(self) -> None:
        type(self).closed = True


def test_quantlab_dashboard_entrypoint_is_dashboard_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("QUANTBET_API_DAILY_LIMIT", "1234")
    monkeypatch.setenv("QUANTBET_CURRENCY", "rsd")
    monkeypatch.setenv("PORT", "9090")

    stop = Event()
    stop.set()
    monkeypatch.setattr(entrypoint, "Event", lambda: stop)
    monkeypatch.setattr(entrypoint, "install_shutdown_handlers", lambda _callback: None)
    monkeypatch.setattr(entrypoint, "configure_logging", lambda _level: None)
    monkeypatch.setattr(entrypoint, "PostgreSQLQuantLabRepository", _Repository)
    monkeypatch.setattr(entrypoint, "QuantLabDashboardService", _Dashboard)
    monkeypatch.setattr(entrypoint, "QuantLabDashboardHTTPService", _Server)

    _Server.started = False
    _Server.closed = False
    entrypoint.main()

    assert _Server.started is True
    assert _Server.closed is True
