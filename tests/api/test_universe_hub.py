"""Navigation-only and authentication regressions for the mobile hub."""

from __future__ import annotations

import base64
import json
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from h2h.api.dashboard import DashboardHTTPService
from h2h.api.universe_hub import MODULES


def test_paused_tournament_has_no_live_link(monkeypatch):
    from h2h.api.universe_hub import render_hub
    monkeypatch.setenv('QUANTBET_KELLY_TOURNAMENT_PAUSED','true')
    html = render_hub()
    assert 'PAUZIRANO · fokus na flat uloge' in html
    assert 'aria-disabled="true"' in html
    assert 'href="https://quantbet-kelly-tournament-production' not in html
    assert 'href="https://quantbet-kellylab-production' in html


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.append({key: value or "" for key, value in attrs})


class CountingDashboard:
    renders = 0

    def render_html(self) -> str:
        self.renders += 1
        return "<html>existing dashboard</html>"


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("QUANTBET_DASHBOARD_PUBLIC", raising=False)
    monkeypatch.setenv("QUANTBET_DASHBOARD_USER", "operator")
    monkeypatch.setenv("QUANTBET_DASHBOARD_PASSWORD", "secret")
    dashboard = CountingDashboard()
    service = DashboardHTTPService(dashboard, host="127.0.0.1", port=0)
    service.start()
    try:
        yield service, dashboard
    finally:
        service.close()


def _url(server: DashboardHTTPService, path: str) -> str:
    return f"http://127.0.0.1:{server.port}{path}"


def _authenticated(url: str) -> Request:
    token = base64.b64encode(b"operator:secret").decode("ascii")
    return Request(url, headers={"Authorization": f"Basic {token}"})


def test_hub_has_all_eight_same_tab_links_and_does_not_render_dashboard(server) -> None:
    service, dashboard = server
    with urlopen(_authenticated(_url(service, "/hub"))) as response:
        html = response.read().decode("utf-8")
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert "script-src" not in response.headers["Content-Security-Policy"]
    parser = Links()
    parser.feed(html)
    assert [link["href"] for link in parser.links] == [module[1] for module in MODULES]
    assert len(parser.links) == 8
    assert all("target" not in link for link in parser.links)
    assert "<iframe" not in html.lower()
    assert "<script" not in html.lower()
    assert dashboard.renders == 0
    assert [module[0] for module in MODULES] == [
        "Production", "Research", "CornerLab", "GoalLab", "H2HLab",
        "CardLab", "KellyLab", "Kelly Tournament",
    ]


def test_hub_uses_existing_dashboard_authentication(server, monkeypatch) -> None:
    service, dashboard = server
    url = _url(service, "/hub")
    with pytest.raises(HTTPError) as denied:
        urlopen(url)
    assert denied.value.code == 401
    assert denied.value.headers["WWW-Authenticate"] == 'Basic realm="QuantBet Dashboard"'
    assert dashboard.renders == 0
    with urlopen(_authenticated(_url(service, "/dashboard"))) as response:
        assert b"existing dashboard" in response.read()
    assert dashboard.renders == 1
    monkeypatch.setenv("QUANTBET_DASHBOARD_PUBLIC", "true")
    with urlopen(url) as response:
        assert response.status == 200


def test_manifest_and_icons_are_valid_static_assets(server) -> None:
    service, dashboard = server
    with urlopen(_url(service, "/hub/manifest.webmanifest")) as response:
        manifest = json.load(response)
        assert response.headers["Content-Type"] == "application/manifest+json"
    assert manifest["start_url"] == "/hub"
    assert manifest["scope"] == "/hub"
    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    for size in (180, 192, 512):
        with urlopen(_url(service, f"/hub/icon-{size}.png")) as response:
            image = response.read()
            assert response.headers["Content-Type"] == "image/png"
            assert image[:8] == b"\x89PNG\r\n\x1a\n"
            assert int.from_bytes(image[16:20], "big") == size
            assert int.from_bytes(image[20:24], "big") == size
    assert dashboard.renders == 0
