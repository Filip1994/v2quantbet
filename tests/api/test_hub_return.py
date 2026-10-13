from __future__ import annotations

from urllib.request import urlopen

from h2h.api.hub_return import HUB_URL
from h2h.api.research_dashboard import ResearchDashboardHTTPService


def test_every_research_html_route_has_one_hub_link_and_json_is_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("QUANTBET_RESEARCH_PUBLIC", "true")

    class Research:
        def render_html(self, _query):
            return "<html><body>Board</body></html>"

        def render_analytics_html(self, _query):
            return "<html><body>Analytics</body></html>"

        def render_model_version_html(self, _version, _query):
            return "<html><body>Model</body></html>"

        def render_league_html(self, _league, _season, _query):
            return "<html><body>League</body></html>"

        def analytics_snapshot(self):
            return {"ok": True}

    service = ResearchDashboardHTTPService(Research(), host="127.0.0.1", port=0)
    service.start()
    try:
        base = f"http://127.0.0.1:{service._server.server_address[1]}"
        for path in (
            "/research",
            "/research/analytics",
            "/research/analytics/model?model_version_id=test",
            "/research/analytics/league?league_id=39&season=2026",
        ):
            with urlopen(base + path) as response:
                body = response.read().decode()
                assert body.count(f'href="{HUB_URL}"') == 1
                assert 'target="_blank"' not in body
        with urlopen(base + "/research/analytics.json") as response:
            assert response.read() == b'{\n  "ok": true\n}'
    finally:
        service.close()
