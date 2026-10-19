"""Static, read-only launcher for the existing QuantBet dashboards."""

from __future__ import annotations

import json
import os
from html import escape


MODULES = (
    ("Production", "/dashboard", "P", "production", "Operativni dashboard"),
    (
        "Research",
        "https://quantbet-research-production.up.railway.app/research",
        "R",
        "research",
        "Istraživanje i analitika",
    ),
    (
        "CornerLab",
        "https://quantbet-quantlab-production.up.railway.app/quantlab?view=dashboard&lab=corner",
        "⌜",
        "corner",
        "QuantLab · korneri",
    ),
    (
        "GoalLab",
        "https://quantbet-quantlab-production.up.railway.app/quantlab?view=dashboard&lab=goal",
        "◎",
        "goal",
        "QuantLab · golovi",
    ),
    (
        "H2HLab",
        "https://quantbet-quantlab-production.up.railway.app/quantlab?view=dashboard&lab=h2h",
        "↔",
        "h2h",
        "QuantLab · međusobni dueli",
    ),
    (
        "CardLab",
        "https://quantbet-quantlab-production.up.railway.app/quantlab?view=dashboard&lab=card",
        "▤",
        "cards",
        "QuantLab · kartoni",
    ),
    (
        "KellyLab",
        "https://quantbet-kellylab-production.up.railway.app/kellylab",
        "K",
        "kelly",
        "Kelly shadow portfolio",
    ),
    (
        "Kelly Tournament",
        "https://quantbet-kelly-tournament-production.up.railway.app/",
        "★",
        "tournament",
        "Turnir Kelly strategija",
    ),
)


def manifest_json() -> bytes:
    return json.dumps(
        {
            "id": "/hub",
            "name": "QuantBet Universe Hub",
            "short_name": "QuantBet",
            "description": "Jedan ulaz u postojeće QuantBet dashboarde.",
            "start_url": "/hub",
            "scope": "/hub",
            "display": "standalone",
            "background_color": "#0a1020",
            "theme_color": "#0a1020",
            "icons": [
                {"src": "/hub/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/hub/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def render_hub() -> str:
    tournament_paused = os.getenv('QUANTBET_KELLY_TOURNAMENT_PAUSED', '').lower() == 'true'
    def card(name, href, symbol, tone, description):
        paused = tournament_paused and tone == 'tournament'
        opening = ('<div class="card tournament" aria-disabled="true">' if paused else
                   '<a class="card ' + tone + '" href="' + escape(href, quote=True) + '">')
        return opening + (
        '<span class="symbol" aria-hidden="true">' + escape(symbol) + '</span>'
        '<span class="copy"><strong>' + escape(name) + '</strong><small>'
        + escape('PAUZIRANO · fokus na flat uloge' if paused else description)
        + '</small></span>' + ('</div>' if paused else '<span class="arrow" aria-hidden="true">↗</span></a>'))
    cards = "".join(
        card(name, href, symbol, tone, description)
        for name, href, symbol, tone, description in MODULES
    )
    return """<!doctype html>
<html lang="sr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0a1020">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="QuantBet">
<link rel="manifest" href="/hub/manifest.webmanifest" crossorigin="use-credentials">
<link rel="apple-touch-icon" href="/hub/icon-180.png">
<title>QuantBet Universe Hub</title>
<style>
:root{color-scheme:dark;--bg:#0a1020;--panel:#121d31;--line:#29405d;--text:#f0f6ff;--muted:#9eb0c7}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;min-width:0;color:var(--text);font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 90% 0%,#193753 0,transparent 42%),var(--bg)}
main{width:min(100%,980px);margin:auto;padding:calc(env(safe-area-inset-top) + 28px) max(18px,env(safe-area-inset-right)) calc(env(safe-area-inset-bottom) + 28px) max(18px,env(safe-area-inset-left))}
header{display:flex;align-items:center;gap:14px;margin-bottom:28px}.brand{display:grid;place-items:center;flex:none;width:52px;height:52px;border-radius:17px;background:#10d7b0;color:#06241f;font-weight:900;font-size:29px;box-shadow:0 10px 32px #10d7b033}.eyebrow{margin:0;color:#42e2c4;font-size:12px;font-weight:750;letter-spacing:.14em;text-transform:uppercase}h1{font-size:clamp(26px,5.5vw,36px);line-height:1.08;margin:3px 0 0;letter-spacing:-.04em}h2{font-size:14px;color:var(--muted);font-weight:600;margin:0 0 12px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.card{min-width:0;min-height:132px;display:flex;flex-direction:column;position:relative;padding:17px;border:1px solid var(--line);border-radius:20px;background:linear-gradient(145deg,#17253d,#101a2b);color:var(--text);text-decoration:none;transition:transform .15s,border-color .15s,background .15s}.card:hover,.card:focus-visible{transform:translateY(-2px);border-color:var(--accent);outline:none}.card:active{transform:scale(.98)}.symbol{display:grid;place-items:center;width:42px;height:42px;border-radius:12px;background:color-mix(in srgb,var(--accent) 17%,transparent);color:var(--accent);font-size:23px;font-weight:800;line-height:1}.copy{min-width:0;margin-top:auto;padding-top:13px}.copy strong,.copy small{display:block;overflow-wrap:anywhere}.copy strong{font-size:16px;line-height:1.2}.copy small{color:var(--muted);font-size:12px;margin-top:4px}.arrow{position:absolute;right:17px;top:17px;color:var(--muted);font-size:19px}
.production{--accent:#4de3ba}.research{--accent:#83b8ff}.corner{--accent:#f6bd6b}.goal{--accent:#a99bff}.h2h{--accent:#7ad5e9}.cards{--accent:#fb8e9b}.kelly{--accent:#b4df77}.tournament{--accent:#ffd86b}
.note{margin:24px 0 0;padding:16px 18px;border:1px solid var(--line);border-radius:16px;background:#101b2d;color:var(--muted);font-size:13px}.note strong{color:var(--text)}
@media(min-width:680px){main{padding-top:52px}.grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.card{min-height:156px;padding:20px}.copy strong{font-size:18px}.copy small{font-size:13px}}
@media(max-width:340px){.grid{grid-template-columns:1fr}.card{min-height:104px}}
@media(prefers-reduced-motion:reduce){.card{transition:none}}
</style></head><body><main>
<header><div class="brand" aria-hidden="true">Q</div><div><p class="eyebrow">QuantBet Universe</p><h1>Dashboard Hub</h1></div></header>
<section aria-labelledby="modules"><h2 id="modules">Izaberi modul</h2><div class="grid">""" + cards + """</div></section>
<p class="note"><strong>Povratak na Hub:</strong> koristi Back / Done u pregledaču ili QuantBet ikonicu na početnom ekranu. Drugi domen može se otvoriti u sistemskom prikazu pregledača.</p>
</main></body></html>"""
