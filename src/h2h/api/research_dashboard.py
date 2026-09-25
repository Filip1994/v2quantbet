"""Read-only HTTP dashboard for QuantBet exposure-blocked research signals."""

from __future__ import annotations

import base64
import hmac
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlsplit

from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository


def _public() -> bool:
    return os.environ.get("QUANTBET_DASHBOARD_PUBLIC", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


class ResearchDashboardService:
    def __init__(self, repository: PostgreSQLResearchSignalRepository) -> None:
        self._repository = repository

    @staticmethod
    def _probability_bucket(value: float) -> str:
        pct = value * 100
        for low in (40, 45, 50, 55, 60, 65, 70):
            if low <= pct < low + 5:
                return f"{low}-{low + 5}%"
        if pct >= 75:
            return "75%+"
        return "<40%"

    @staticmethod
    def _ev_bucket(value: float) -> str:
        pct = value * 100
        if pct < 10:
            return "7-10%"
        if pct < 15:
            return "10-15%"
        if pct < 20:
            return "15-20%"
        if pct < 30:
            return "20-30%"
        return "30%+"

    @staticmethod
    def _aggregate(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row[key])].append(row)
        out: list[dict[str, Any]] = []
        for bucket, items in grouped.items():
            settled = [x for x in items if x["counterfactual_outcome"] is not None]
            wins = sum(x["counterfactual_outcome"] == "WIN" for x in settled)
            pnl = sum(int(x["counterfactual_pnl_minor"] or 0) for x in settled)
            clvs = [int(x["shadow_clv_ppm"]) for x in items if x["shadow_clv_ppm"] is not None]
            out.append(
                {
                    "bucket": bucket,
                    "signals": len(items),
                    "settled": len(settled),
                    "wins": wins,
                    "hit_rate": None if not settled else wins / len(settled),
                    "pnl_minor": pnl,
                    "avg_clv_ppm": None if not clvs else sum(clvs) / len(clvs),
                }
            )
        return out

    def snapshot(self, *, provider_fixture_id: str | None = None) -> dict[str, Any]:
        rows = self._repository.signals(provider_fixture_id=provider_fixture_id)
        for row in rows:
            row["probability_bucket"] = self._probability_bucket(row["model_probability"])
            row["ev_bucket"] = self._ev_bucket(row["expected_value"])
        settled = [x for x in rows if x["counterfactual_outcome"] is not None]
        clvs = [int(x["shadow_clv_ppm"]) for x in rows if x["shadow_clv_ppm"] is not None]
        return {
            "generated_at": datetime.now(UTC),
            "filter_provider_fixture_id": provider_fixture_id,
            "counts": {
                "signals": len(rows),
                "fixtures": len({x["provider_fixture_id"] for x in rows}),
                "settled": len(settled),
                "pending": len(rows) - len(settled),
                "wins": sum(x["counterfactual_outcome"] == "WIN" for x in settled),
                "losses": sum(x["counterfactual_outcome"] == "LOSS" for x in settled),
                "voids": sum(x["counterfactual_outcome"] == "VOID" for x in settled),
                "eventually_registered": sum(
                    x["eventually_registered_pick_id"] is not None for x in rows
                ),
            },
            "counterfactual_pnl_minor": sum(
                int(x["counterfactual_pnl_minor"] or 0) for x in settled
            ),
            "average_shadow_clv_ppm": None if not clvs else sum(clvs) / len(clvs),
            "probability_buckets": self._aggregate(rows, "probability_bucket"),
            "ev_buckets": self._aggregate(rows, "ev_bucket"),
            "signals": rows,
        }

    @staticmethod
    def _pct(value: Any) -> str:
        return "—" if value is None else f"{float(value) * 100:.2f}%"

    @staticmethod
    def _clv(value: Any) -> str:
        return "—" if value is None else f"{float(value) / 10000:+.2f}%"

    @staticmethod
    def _money(value: Any) -> str:
        return "—" if value is None else f"{int(value) / 100:,.2f} RSD"

    @staticmethod
    def _dt(value: Any) -> str:
        if value is None:
            return "—"
        return value.astimezone(UTC).strftime("%d %b %Y · %H:%M UTC")

    def render_html(self, *, provider_fixture_id: str | None = None) -> str:
        data = self.snapshot(provider_fixture_id=provider_fixture_id)
        c = data["counts"]
        rows = []
        for item in data["signals"]:
            fixture = f"{item['home_team']} – {item['away_team']}"
            score = (
                "—"
                if item["regulation_home_goals"] is None
                else f"{item['regulation_home_goals']}–{item['regulation_away_goals']}"
            )
            registered = (
                "NO"
                if item["eventually_registered_pick_id"] is None
                else f"YES · {item['eventually_registered_market']} {item['eventually_registered_selection']}"
            )
            rows.append(
                "<tr>"
                f"<td><strong>{escape(fixture)}</strong><small>{escape(item['competition_name'])} · "
                f"{escape(item['country'])}<br>ID {escape(item['provider_fixture_id'])} · "
                f"{escape(self._dt(item['kickoff_at']))}</small></td>"
                f"<td><strong>{escape(item['market'])} {escape(item['selection'])}</strong>"
                f"<small>{escape(item['bookmaker_key'])} · blocked {escape(self._dt(item['blocked_at']))}</small></td>"
                f"<td class='num'><strong>{item['entry_odd']:.2f}</strong>"
                f"<small>shadow close {('—' if item['shadow_closing_odd'] is None else f'{item['shadow_closing_odd']:.2f}')}</small></td>"
                f"<td class='num'><strong>{self._pct(item['model_probability'])}</strong>"
                f"<small>market {self._pct(item['market_fair_probability'])}</small></td>"
                f"<td class='num'><strong>{self._pct(item['edge'])}</strong>"
                f"<small>EV {self._pct(item['expected_value'])}</small></td>"
                f"<td class='num'><strong>{self._clv(item['shadow_clv_ppm'])}</strong>"
                "<small>shadow same-book</small></td>"
                f"<td><strong>{escape(str(item['counterfactual_outcome'] or 'PENDING'))}</strong>"
                f"<small>{escape(score)}</small></td>"
                f"<td class='num'><strong>{self._money(item['counterfactual_pnl_minor'])}</strong></td>"
                f"<td><strong>{escape(registered)}</strong><small>{escape(item['capture_source'])}</small></td>"
                "</tr>"
            )
        table_rows = "".join(rows) or "<tr><td colspan='9'>No research signals.</td></tr>"

        def bucket_rows(items: list[dict[str, Any]]) -> str:
            return "".join(
                "<tr>"
                f"<td>{escape(x['bucket'])}</td><td class='num'>{x['signals']}</td>"
                f"<td class='num'>{x['settled']}</td>"
                f"<td class='num'>{self._pct(x['hit_rate'])}</td>"
                f"<td class='num'>{self._clv(x['avg_clv_ppm'])}</td>"
                f"<td class='num'>{self._money(x['pnl_minor'])}</td>"
                "</tr>"
                for x in items
            )

        filter_text = (
            ""
            if provider_fixture_id is None
            else f"<p class='filter'>Filtered provider fixture: <strong>{escape(provider_fixture_id)}</strong> · <a href='/research'>clear</a></p>"
        )
        avg_clv = self._clv(data["average_shadow_clv_ppm"])
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantBet Research</title>
<style>
:root{{--bg:#0a0d12;--panel:#121821;--line:#273244;--text:#edf2f8;--muted:#91a0b4;--good:#42d392;--warn:#f6c453}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 system-ui,sans-serif}}
main{{max-width:1900px;margin:auto;padding:22px}}h1{{margin:0 0 4px;font-size:26px}}p{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(6,minmax(140px,1fr));gap:8px;margin:16px 0}}
.card,.panel{{background:var(--panel);border:1px solid var(--line)}}.card{{padding:12px}}.card span,small{{display:block;color:var(--muted)}}.card strong{{font-size:18px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}}.panel h2{{font-size:14px;padding:12px;margin:0;border-bottom:1px solid var(--line)}}
.wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:850px}}th,td{{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--muted);font-size:10px;text-transform:uppercase}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.signal-table{{min-width:1450px}}a{{color:#88b4ff}}.filter{{background:var(--panel);padding:8px 10px;border:1px solid var(--line)}}
@media(max-width:1000px){{.cards{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>QuantBet · Exposure Research</h1>
<p>Shadow ledger only — no bankroll reservation, no betting action. Search by provider fixture ID with <code>?fixture=1577950</code>.</p>
{filter_text}
<section class="cards">
<div class="card"><span>Signals</span><strong>{c['signals']}</strong></div>
<div class="card"><span>Fixtures</span><strong>{c['fixtures']}</strong></div>
<div class="card"><span>Settled / Pending</span><strong>{c['settled']} / {c['pending']}</strong></div>
<div class="card"><span>W / L / V</span><strong>{c['wins']} / {c['losses']} / {c['voids']}</strong></div>
<div class="card"><span>Avg shadow CLV</span><strong>{escape(avg_clv)}</strong></div>
<div class="card"><span>Flat-stake shadow P/L</span><strong>{escape(self._money(data['counterfactual_pnl_minor']))}</strong></div>
</section>
<section class="grid">
<article class="panel"><h2>Model probability buckets</h2><div class="wrap"><table><thead><tr><th>Bucket</th><th class="num">Signals</th><th class="num">Settled</th><th class="num">Hit rate</th><th class="num">Avg CLV</th><th class="num">P/L</th></tr></thead><tbody>{bucket_rows(data['probability_buckets'])}</tbody></table></div></article>
<article class="panel"><h2>Expected-value buckets</h2><div class="wrap"><table><thead><tr><th>Bucket</th><th class="num">Signals</th><th class="num">Settled</th><th class="num">Hit rate</th><th class="num">Avg CLV</th><th class="num">P/L</th></tr></thead><tbody>{bucket_rows(data['ev_buckets'])}</tbody></table></div></article>
</section>
<section class="panel"><h2>Exposure-blocked signal ledger</h2><div class="wrap"><table class="signal-table"><thead><tr>
<th>Fixture</th><th>Signal</th><th class="num">Odds</th><th class="num">Probability</th><th class="num">Value</th><th class="num">Shadow CLV</th><th>Outcome</th><th class="num">Shadow P/L</th><th>Later registered?</th>
</tr></thead><tbody>{table_rows}</tbody></table></div></section>
<p>Shadow CLV uses the latest stored same-series, same-source pre-kickoff quote. It is research evidence and is intentionally separate from official registered-pick CLV.</p>
</main></body></html>"""


class ResearchDashboardHTTPService:
    def __init__(
        self, dashboard: ResearchDashboardService, *, host: str, port: int
    ) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                fixture = query.get("fixture", [None])[0]
                if parsed.path == "/livez":
                    service._json(self, 200, {"live": True})
                    return
                if parsed.path in {"/", "/research"}:
                    if not service._authorize(self):
                        return
                    try:
                        service._html(
                            self,
                            200,
                            dashboard.render_html(provider_fixture_id=fixture),
                        )
                    except ValueError as exc:
                        service._json(self, 400, {"error": str(exc)})
                    return
                if parsed.path == "/api/research-signals":
                    if not service._authorize(self):
                        return
                    try:
                        service._json(
                            self,
                            200,
                            dashboard.snapshot(provider_fixture_id=fixture),
                        )
                    except ValueError as exc:
                        service._json(self, 400, {"error": str(exc)})
                    return
                service._json(self, 404, {"error": "not_found"})

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @staticmethod
    def _default(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"not JSON serializable: {type(value).__name__}")

    @classmethod
    def _json(cls, handler: BaseHTTPRequestHandler, status: int, body: Any) -> None:
        encoded = json.dumps(body, default=cls._default).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    @staticmethod
    def _html(handler: BaseHTTPRequestHandler, status: int, body: str) -> None:
        encoded = body.encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header(
            "Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"
        )
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    @staticmethod
    def _authorize(handler: BaseHTTPRequestHandler) -> bool:
        if _public():
            return True
        password = os.environ.get("QUANTBET_DASHBOARD_PASSWORD", "")
        username = os.environ.get("QUANTBET_DASHBOARD_USER", "quantbet")
        if not password:
            ResearchDashboardHTTPService._json(
                handler, 404, {"error": "not_found"}
            )
            return False
        supplied_user = supplied_password = ""
        authorization = handler.headers.get("Authorization", "")
        if authorization.startswith("Basic "):
            try:
                decoded = base64.b64decode(
                    authorization[6:], validate=True
                ).decode()
                supplied_user, supplied_password = decoded.split(":", 1)
            except (ValueError, UnicodeDecodeError):
                pass
        if hmac.compare_digest(supplied_user, username) and hmac.compare_digest(
            supplied_password, password
        ):
            return True
        encoded = b'{"error":"authentication_required"}'
        handler.send_response(401)
        handler.send_header(
            "WWW-Authenticate", 'Basic realm="QuantBet Research"'
        )
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)
        return False

    def start(self) -> None:
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
