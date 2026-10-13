"""A one-tap return link for existing read-only dashboard HTML pages."""

HUB_URL = "https://quantbet-dashboard-production.up.railway.app/hub"

HUB_LINK = (
    '<a id="quantbet-hub-return" href="' + HUB_URL + '" '
    'aria-label="Vrati se na QuantBet Hub" '
    'style="position:fixed;z-index:2147483647;right:max(12px,env(safe-area-inset-right));'
    'bottom:max(12px,env(safe-area-inset-bottom));display:flex;align-items:center;'
    'justify-content:center;min-width:88px;min-height:46px;padding:10px 16px;'
    'border-radius:999px;background:#10d7b0;color:#06241f;'
    'box-shadow:0 6px 24px #0009;font:700 15px/1.2 -apple-system,BlinkMacSystemFont,'
    'Segoe UI,sans-serif;text-decoration:none">⌂ Hub</a>'
)


def with_hub_return(body: str) -> str:
    """Add the link to HTML without changing dashboard data or scripts."""
    if 'id="quantbet-hub-return"' in body:
        return body
    closing = body.rfind("</body>")
    if closing < 0:
        return body
    return body[:closing] + HUB_LINK + body[closing:]
