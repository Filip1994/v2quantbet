from __future__ import annotations

from urllib.request import urlopen

from h2h.api.hub_return import HUB_URL
from h2h.api.kellylab_dashboard import KellyLabHTTPService


def test_kellylab_html_has_hub_link_and_json_is_unchanged() -> None:
    class Kelly:
        def render_html(self, _query):
            return "<html><body>Kelly</body></html>"

        def snapshot(self):
            return {"ok": True}

    service = KellyLabHTTPService(Kelly(), host="127.0.0.1", port=0)
    service.start()
    try:
        base = f"http://127.0.0.1:{service._server.server_address[1]}"
        with urlopen(base + "/kellylab") as response:
            body = response.read().decode()
            assert body.count(f'href="{HUB_URL}"') == 1
            assert 'target="_blank"' not in body
        with urlopen(base + "/kellylab.json") as response:
            assert response.read() == b'{\n  "ok": true\n}'
    finally:
        service.close()
