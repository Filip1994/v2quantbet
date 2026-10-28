"""Regression: observed crawler cannot execute expensive Research analytics."""
from http.client import HTTPConnection

from h2h.api.research_dashboard import ResearchDashboardHTTPService


class _StubDashboard:
    def render_html(self, _query: str) -> str:
        return "<html>research-ok</html>"

    def corner_snapshot(self, _query: str):
        raise AssertionError("crawler must not execute corner snapshot query")


def test_research_blocks_meta_crawler_but_stays_public(monkeypatch) -> None:
    monkeypatch.setenv("QUANTBET_RESEARCH_PUBLIC", "true")
    server = ResearchDashboardHTTPService(_StubDashboard(), host="127.0.0.1", port=0)
    server.start()
    try:
        port = server._server.server_port
        for path, agent, status, expected in (
            ("/research/analytics/corners", "meta-externalagent/1.1", 403, b"crawler_blocked"),
            ("/robots.txt", "any bot", 200, b"Disallow: /"),
            ("/livez", "browser", 200, b"ok"),
            ("/research", "Mozilla/5.0", 200, b"research-ok"),
        ):
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                conn.request("GET", path, headers={"User-Agent": agent})
                response = conn.getresponse()
                assert response.status == status, path
                assert expected in response.read(), path
            finally:
                conn.close()
    finally:
        server.close()
