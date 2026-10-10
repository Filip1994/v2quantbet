"""Client disconnect regressions for the read-only football dashboards.

A browser switching mobile/desktop modes can abort the request while HTML is
still rendering or while the server is writing it. Those aborts are not 503s
and must not trigger a second response on a closed socket.
"""

from __future__ import annotations

from http.client import HTTPConnection, RemoteDisconnected

import pytest

from h2h.api.research_dashboard import ResearchDashboardHTTPService
from h2h.quantlab.dashboard import QuantLabDashboardHTTPService


@pytest.mark.parametrize(
    ("service_class", "public_setting", "path"),
    [
        (ResearchDashboardHTTPService, "QUANTBET_RESEARCH_PUBLIC", "/research"),
        (QuantLabDashboardHTTPService, "QUANTBET_QUANTLAB_PUBLIC", "/quantlab"),
    ],
)
@pytest.mark.parametrize("render_result", ["success", "invalid", "failure"])
@pytest.mark.parametrize("disconnect", [BrokenPipeError, ConnectionResetError])
def test_disconnected_get_does_not_send_second_response(
    monkeypatch: pytest.MonkeyPatch,
    service_class: type,
    public_setting: str,
    path: str,
    render_result: str,
    disconnect: type[OSError],
) -> None:
    monkeypatch.setenv(public_setting, "true")

    class Dashboard:
        @staticmethod
        def render_html(_query: str = "") -> str:
            if render_result == "invalid":
                raise ValueError("invalid query")
            if render_result == "failure":
                raise RuntimeError("backend unavailable")
            return "<html>ok</html>"

    attempted_statuses: list[int] = []

    def simulated_disconnected_write(_handler: object, status: int, *_args: object) -> None:
        attempted_statuses.append(status)
        raise disconnect("peer closed")

    monkeypatch.setattr(service_class, "_text", staticmethod(simulated_disconnected_write))
    service = service_class(Dashboard(), host="127.0.0.1", port=0)
    service.start()
    connection = HTTPConnection("127.0.0.1", service._server.server_address[1], timeout=5)
    try:
        connection.request("GET", path)
        with pytest.raises(RemoteDisconnected):
            connection.getresponse()
        assert attempted_statuses == [
            200 if render_result == "success" else 400 if render_result == "invalid" else 503
        ]
    finally:
        connection.close()
        service.close()
