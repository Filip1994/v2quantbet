"""Read-only KellyLab dashboard for the Research shadow portfolio."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlsplit

from h2h.api.dashboard_time import local_iso, local_time


def _money(minor: Any) -> str:
    if minor is None:
        return "—"
    return f"{int(minor) / 100:,.2f} RSD".replace(",", " ")


def _signed_money(minor: Any) -> str:
    if minor is None:
        return "—"
    return f"{int(minor) / 100:+,.2f} RSD".replace(",", " ")


def _pct(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    number = float(value)
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.2f}%"


def _probability(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.2f}%"


def _fraction(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.2f}%"


class KellyLabDashboardService:
    def __init__(self, repository: Any, *, clock=lambda: datetime.now(UTC)) -> None:
        self._repository = repository
        self._clock = clock

    def snapshot(self) -> dict[str, Any]:
        return self._repository.portfolio_snapshot()

    def render_html(self, query: str = "") -> str:
        payload = self.snapshot()
        portfolio = payload["portfolio"]
        all_rows = payload["picks"]
        params = parse_qs(query, keep_blank_values=True)
        tab = params.get("tab", ["active"])[0].strip().casefold()
        if tab not in {"active", "history", "all"}:
            tab = "active"

        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must be timezone-aware")
        now = now.astimezone(UTC)

        if tab == "history":
            rows = [
                row
                for row in all_rows
                if row["outcome"] in {"WIN", "LOSS", "VOID"}
            ]
            title = "Settled KellyLab history"
        elif tab == "all":
            rows = list(all_rows)
            title = "All KellyLab clones"
        else:
            rows = [row for row in all_rows if row["outcome"] == "PENDING"]
            title = "Active KellyLab clones"

        def metric_class(value: Any) -> str:
            if value is None or float(value) == 0:
                return "neutral"
            return "positive" if float(value) > 0 else "negative"

        cards = [
            ("Starting bankroll", _money(portfolio["starting_bankroll_minor"]), "neutral"),
            (
                "Kelly bankroll",
                _money(portfolio["kelly_bankroll_minor"]),
                metric_class(portfolio["kelly_pnl_minor"]),
            ),
            (
                "Kelly P/L",
                _signed_money(portfolio["kelly_pnl_minor"]),
                metric_class(portfolio["kelly_pnl_minor"]),
            ),
            (
                "Flat control",
                _money(portfolio["flat_bankroll_minor"]),
                metric_class(portfolio["flat_pnl_minor"]),
            ),
            (
                "Flat P/L",
                _signed_money(portfolio["flat_pnl_minor"]),
                metric_class(portfolio["flat_pnl_minor"]),
            ),
            (
                "Kelly return",
                _pct(portfolio["kelly_return_pct"], signed=True),
                metric_class(portfolio["kelly_return_pct"]),
            ),
            (
                "Max drawdown",
                _pct(-float(portfolio["kelly_max_drawdown_pct"])),
                "negative" if portfolio["kelly_max_drawdown_pct"] else "neutral",
            ),
            ("Open Kelly stake", _money(portfolio["open_stake_minor"]), "neutral"),
        ]
        cards_html = "".join(
            f'<div class="card"><small>{escape(label)}</small>'
            f'<b class="{css}">{escape(value)}</b></div>'
            for label, value, css in cards
        )

        rows_html: list[str] = []
        for row in rows:
            outcome = str(row["outcome"])
            score = "—"
            if (
                row.get("regulation_home_goals") is not None
                and row.get("regulation_away_goals") is not None
            ):
                score = (
                    f'{int(row["regulation_home_goals"])} : '
                    f'{int(row["regulation_away_goals"])}'
                )
            gap = float(row["calibration_gap"]) * 100
            late = bool((row.get("source_payload") or {}).get("late_materialization"))
            materialization = "late replay" if late else "live capture"
            rows_html.append(
                f'<tr class="row-{escape(outcome.casefold())}">'
                f'<td class="match"><b>{escape(str(row["home_team"]))} – '
                f'{escape(str(row["away_team"]))}</b><small>'
                f'{escape(str(row["competition_name"]))}</small></td>'
                f'<td><b>{escape(str(row["market"]))} '
                f'{escape(str(row["selection"]))}</b></td>'
                f'<td><b>{float(row["odds"]):.2f}</b><small>'
                f'{escape(str(row["bookmaker"]))}</small></td>'
                f'<td>{_probability(row["model_probability"])}</td>'
                f'<td><b>{_probability(row["kelly_probability"])}</b>'
                f'<small>{gap:+.2f} pp calibration</small></td>'
                f'<td>{_fraction(row["raw_kelly_fraction"])}</td>'
                f'<td><b>{_fraction(row["applied_kelly_fraction"])}</b></td>'
                f'<td>{_money(row["bankroll_before_minor"])}</td>'
                f'<td><b>{_money(row["stake_minor"])}</b><small>'
                f'{escape(str(row["decision"]))}</small></td>'
                f'<td>{_money(row["flat_stake_minor"])}</td>'
                f'<td><b>{escape(outcome)}</b><small>{escape(score)}</small></td>'
                f'<td class="{metric_class(row["kelly_pnl_minor"])}">'
                f'<b>{_signed_money(row["kelly_pnl_minor"])}</b></td>'
                f'<td class="{metric_class(row["flat_pnl_minor"])}">'
                f'{_signed_money(row["flat_pnl_minor"])}</td>'
                f'<td>{escape(local_time(row["source_decision_at"], "%Y-%m-%d %H:%M"))}'
                f'<small>{escape(materialization)}</small></td>'
                f'<td>{escape(local_time(row["kickoff_at"], "%Y-%m-%d %H:%M"))}</td>'
                "</tr>"
            )

        body = "".join(rows_html)
        if not body:
            body = '<tr><td class="empty" colspan="15">No KellyLab rows in this view.</td></tr>'

        started = escape(local_iso(portfolio["started_at"]))
        fraction = _fraction(portfolio["kelly_fraction"])
        cap = _fraction(portfolio["max_bet_fraction"])
        flat = _money(portfolio["flat_stake_minor"])
        active_class = "active" if tab == "active" else ""
        history_class = "active" if tab == "history" else ""
        all_class = "active" if tab == "all" else ""

        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantBet KellyLab</title>
<style>
:root{{--bg:#111315;--panel:#181b1f;--line:#30363d;--text:#eceff1;
--muted:#9299a1;--win:#69c98f;--loss:#e06f78;--accent:#d8dcdf}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);
font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1900px;margin:auto;padding:24px}}
header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}}
h1{{margin:4px 0;font-size:27px}}p,small{{color:var(--muted)}}a{{color:#d8dcdf}}
.badge{{border:1px solid #43505a;border-radius:999px;padding:7px 10px;font-size:11px}}
.cards{{display:grid;grid-template-columns:repeat(8,minmax(125px,1fr));gap:9px;margin:16px 0}}
.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px}}
.card{{padding:13px}}.card small{{text-transform:uppercase;font-size:9px;letter-spacing:.08em}}
.card b{{display:block;font-size:18px;margin-top:7px}}.positive{{color:var(--win)}}
.negative{{color:var(--loss)}}.neutral{{color:var(--text)}}nav{{display:flex;gap:7px;margin:12px 0}}
nav a{{text-decoration:none;border:1px solid #343b42;border-radius:8px;padding:8px 11px}}
nav a.active{{background:#252b30;color:#fff}}.panel{{overflow:hidden}}.table{{overflow:auto;max-height:70vh}}
table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:10px 11px;
border-bottom:1px solid #272c31;white-space:nowrap;text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:#1b1f23;color:#9aa1a8;text-transform:uppercase;
font-size:9px;letter-spacing:.05em}}td.match{{min-width:230px}}td small{{display:block;margin-top:4px}}
.row-win{{box-shadow:inset 3px 0 var(--win)}}.row-loss{{box-shadow:inset 3px 0 var(--loss)}}
.row-pending{{box-shadow:inset 3px 0 #d6aa55}}.empty{{text-align:center;padding:34px!important;
color:var(--muted)}}footer{{color:#7f878e;font-size:11px;margin-top:12px;line-height:1.6}}
@media(max-width:1100px){{.cards{{grid-template-columns:repeat(2,1fr)}}main{{padding:14px}}}}
</style></head><body><main>
<header><div><small>KELLYLAB_RESEARCH_V1 · SHADOW ONLY</small><h1>KellyLab</h1>
<p>Research clones · point-in-time bucket calibration · Quarter Kelly · 1% hard cap</p></div>
<div class="badge">Started {started}</div></header>
<section class="cards">{cards_html}</section>
<nav><a class="{active_class}" href="/kellylab?tab=active">Active ({portfolio["active_count"]})</a>
<a class="{history_class}" href="/kellylab?tab=history">History ({portfolio["settled_count"]})</a>
<a class="{all_class}" href="/kellylab?tab=all">All ({portfolio["pick_count"]})</a>
<a href="/kellylab.json">JSON</a></nav>
<section class="panel"><div style="padding:12px 14px;border-bottom:1px solid var(--line)">
<b>{escape(title)}</b></div><div class="table"><table><thead><tr>
<th>Match</th><th>Pick</th><th>Odds</th><th>Model P</th><th>Kelly P</th>
<th>Raw Kelly</th><th>Applied</th><th>Bankroll before</th><th>Kelly stake</th>
<th>Flat stake</th><th>Result</th><th>Kelly P/L</th><th>Flat P/L</th>
<th>Decision</th><th>Kickoff</th></tr></thead><tbody>{body}</tbody></table></div></section>
<footer>Starting bankroll: {_money(portfolio["starting_bankroll_minor"])} ·
Kelly fraction: {fraction} · max bet: {cap} · flat control: {flat}. Kelly stake uses only
results known before the Research decision timestamp; later outcomes cannot alter the frozen stake.
Times: Europe/Belgrade.</footer>
</main></body></html>"""


class KellyLabHTTPService:
    def __init__(self, dashboard: KellyLabDashboardService, *, host: str, port: int) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path == "/livez":
                    service._text(self, 200, "ok\n", "text/plain; charset=utf-8")
                    return
                if parsed.path not in {"/", "/kellylab", "/kellylab.json"}:
                    service._text(self, 404, "not_found\n", "text/plain; charset=utf-8")
                    return
                try:
                    if parsed.path == "/kellylab.json":
                        body = json.dumps(
                            dashboard.snapshot(),
                            ensure_ascii=False,
                            indent=2,
                            default=service._json_default,
                        )
                        content_type = "application/json; charset=utf-8"
                    else:
                        body = dashboard.render_html(parsed.query)
                        content_type = "text/html; charset=utf-8"
                    service._text(self, 200, body, content_type)
                except Exception as exc:  # noqa: BLE001 - bounded read-only failure response
                    service._text(
                        self,
                        503,
                        type(exc).__name__ + "\n",
                        "text/plain; charset=utf-8",
                    )

            def do_POST(self) -> None:
                service._text(self, 405, "read_only\n", "text/plain; charset=utf-8")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "as_tuple"):
            return float(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    @staticmethod
    def _text(
        handler: BaseHTTPRequestHandler,
        status: int,
        body: str,
        content_type: str,
    ) -> None:
        encoded = body.encode()
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
