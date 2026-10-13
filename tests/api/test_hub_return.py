from __future__ import annotations

from urllib.request import urlopen

from h2h.api.dashboard import DashboardHTTPService
from h2h.api.hub_return import HUB_URL, with_hub_return
from h2h.quantlab.dashboard import QuantLabDashboardHTTPService


def test_hub_return_is_one_same_tab_link() -> None:
    html = with_hub_return("<html><body><main>Data</main></body></html>")
    assert html.count('id="quantbet-hub-return"') == 1
    assert f'href="{HUB_URL}"' in html
    assert 'target="_blank"' not in html
    assert with_hub_return(html) == html
    assert with_hub_return('{"data":true}') == '{"data":true}'


def test_production_and_all_quantlab_labs_show_return_link(monkeypatch) -> None:
    monkeypatch.setenv("QUANTBET_DASHBOARD_PUBLIC", "true")
    monkeypatch.setenv("QUANTBET_QUANTLAB_PUBLIC", "true")

    class Production:
        def render_html(self):
            return "<html><body>Production</body></html>"

    class QuantLab:
        def render_html(self, _query):
            return "<html><body>QuantLab</body></html>"

    production = DashboardHTTPService(Production(), host="127.0.0.1", port=0)
    quantlab = QuantLabDashboardHTTPService(QuantLab(), host="127.0.0.1", port=0)
    production.start()
    quantlab.start()
    try:
        quantlab_port = quantlab._server.server_address[1]
        paths = [f"http://127.0.0.1:{production.port}/dashboard"] + [
            f"http://127.0.0.1:{quantlab_port}/quantlab?lab={lab}"
            for lab in ("corner", "goal", "h2h", "card")
        ]
        for path in paths:
            with urlopen(path) as response:
                assert f'href="{HUB_URL}"'.encode() in response.read()
        with urlopen(f"http://127.0.0.1:{production.port}/hub") as response:
            assert b'quantbet-hub-return' not in response.read()
    finally:
        production.close()
        quantlab.close()
