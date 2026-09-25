"""Read-only research dashboard for exposure-blocked shadow signals."""

from __future__ import annotations

import base64
import hmac
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlsplit

from h2h.api.dashboard import dashboard_is_public
from h2h.domain.settlement import realized_clv_ppm
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _outcome(row: dict[str, Any]) -> str:
    if row.get("correction_required"):
        return "CORRECTION"
    classification = row.get("result_classification")
    if classification is None:
        return "PENDING"
    if classification == "NON_PLAYED_VOIDABLE":
        return "VOID"
    if classification != "PLAYED_SETTLEABLE":
        return "UNAVAILABLE"
    home = row.get("regulation_home_goals")
    away = row.get("regulation_away_goals")
    if home is None or away is None:
        return "UNAVAILABLE"
    total = int(home) + int(away)
    market, selection = row["market"], row["selection"]
    if market == "OU_25" and selection == "OVER":
        won = total >= 3
    elif market == "OU_25" and selection == "UNDER":
        won = total <= 2
    elif market == "BTTS" and selection == "YES":
        won = int(home) >= 1 and int(away) >= 1
    elif market == "BTTS" and selection == "NO":
        won = int(home) == 0 or int(away) == 0
    else:
        return "UNAVAILABLE"
    return "WIN" if won else "LOSS"


def _unit_pnl(row: dict[str, Any], outcome: str) -> Decimal | None:
    odd = row.get("entry_odd")
    if odd is None:
        return None
    if outcome == "WIN":
        return Decimal(odd) - Decimal(1)
    if outcome == "LOSS":
        return Decimal(-1)
    if outcome == "VOID":
        return Decimal(0)
    return None


def _probability_bucket(value: float) -> str:
    pct = max(0.0, min(100.0, float(value) * 100.0))
    if pct >= 75:
        return "75%+"
    lower = int(pct // 5) * 5
    return f"{lower}-{lower + 5}%"


class ResearchDashboardService:
    def __init__(self, repository: PostgreSQLResearchSignalRepository) -> None:
        self._repository = repository

    def snapshot(self, *, provider_fixture_id: str | None = None) -> dict[str, Any]:
        rows = [dict(row) for row in self._repository.rows()]
        if provider_fixture_id:
            rows = [
                row for row in rows
                if str(row.get("provider_fixture_id")) == str(provider_fixture_id)
            ]
        for row in rows:
            closing = row.get("closing_odd")
            row["clv_ppm"] = (
                None
                if closing is None
                else realized_clv_ppm(Decimal(row["entry_odd"]), Decimal(closing))
            )
            kickoff = row.get("kickoff_at")
            closing_observed = row.get("closing_observed_at")
            row["closing_age_seconds"] = (
                None
                if kickoff is None or closing_observed is None
                else int((kickoff - closing_observed).total_seconds())
            )
            row["outcome"] = _outcome(row)
            row["unit_pnl"] = _unit_pnl(row, row["outcome"])

        first_by_fixture: dict[str, dict[str, Any]] = {}
        for row in sorted(rows, key=lambda item: (item["blocked_at"], item["signal_id"])):
            first_by_fixture.setdefault(row["fixture_id"], row)
        primary = tuple(first_by_fixture.values())
        settled = [row for row in primary if row["outcome"] in {"WIN", "LOSS", "VOID"}]
        clv_rows = [row for row in primary if row["clv_ppm"] is not None]
        roi = (
            None
            if not settled
            else sum((row["unit_pnl"] or Decimal(0)) for row in settled) / Decimal(len(settled))
        )
        average_clv = (
            None
            if not clv_rows
            else sum(int(row["clv_ppm"]) for row in clv_rows) / len(clv_rows)
        )
        positive_clv_rate = (
            None
            if not clv_rows
            else sum(int(row["clv_ppm"]) > 0 for row in clv_rows) / len(clv_rows)
        )

        buckets: dict[str, dict[str, Any]] = {}
        for row in primary:
            key = _probability_bucket(float(row["model_probability"]))
            bucket = buckets.setdefault(
                key,
                {"signals": 0, "settled": 0, "wins": 0, "pnl": Decimal(0), "clv": []},
            )
            bucket["signals"] += 1
            if row["outcome"] in {"WIN", "LOSS", "VOID"}:
                bucket["settled"] += 1
                bucket["wins"] += row["outcome"] == "WIN"
                bucket["pnl"] += row["unit_pnl"] or Decimal(0)
            if row["clv_ppm"] is not None:
                bucket["clv"].append(int(row["clv_ppm"]))

        bucket_rows = []
        for key, value in sorted(buckets.items(), key=lambda item: item[0]):
            settled_count = int(value["settled"])
            clvs = value["clv"]
            bucket_rows.append(
                {
                    "bucket": key,
                    "signals": int(value["signals"]),
                    "settled": settled_count,
                    "hit_rate": None if not settled_count else int(value["wins"]) / settled_count,
                    "unit_roi": None if not settled_count else value["pnl"] / settled_count,
                    "avg_clv_ppm": None if not clvs else sum(clvs) / len(clvs),
                }
            )

        return {
            "generated_at": datetime.now(UTC),
            "rows": tuple(rows),
            "primary_rows": primary,
            "bucket_rows": tuple(bucket_rows),
            "summary": {
                "raw_signals": len(rows),
                "unique_fixtures": len(first_by_fixture),
                "settled_primary": len(settled),
                "clv_primary": len(clv_rows),
                "unit_roi": roi,
                "average_clv_ppm": average_clv,
                "positive_clv_rate": positive_clv_rate,
            },
        }

    @staticmethod
    def _pct(value: Any) -> str:
        if value is None:
            return "—"
        return f"{float(value) * 100:+.2f}%"

    @staticmethod
    def _prob(value: Any) -> str:
        if value is None:
            return "—"
        return f"{float(value) * 100:.2f}%"

    @staticmethod
    def _odd(value: Any) -> str:
        return "—" if value is None else f"{Decimal(value):.2f}"

    @staticmethod
    def _dt(value: Any) -> str:
        if not isinstance(value, datetime):
            return "—"
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")

    @staticmethod
    def _clv(value: Any) -> str:
        if value is None:
            return "—"
        return f"{float(value) / 10000:+.2f}%"

    @staticmethod
    def _roi(value: Any) -> str:
        if value is None:
            return "—"
        return f"{float(value) * 100:+.2f}%"

    def render_html(self) -> str:
        data = self.snapshot()
        summary = data["summary"]
        rows_html = []
        for row in data["rows"]:
            outcome = str(row["outcome"])
            pnl = row["unit_pnl"]
            close_age = row["closing_age_seconds"]
            rows_html.append(
                "<tr>"
                f"<td><code>{escape(str(row['provider_fixture_id']))}</code>"
                f"<small>{escape(str(row['fixture_id']))}</small></td>"
                f"<td><strong>{escape(str(row['home_team']))} – {escape(str(row['away_team']))}</strong>"
                f"<small>{escape(str(row['competition_name']))} · {escape(self._dt(row['kickoff_at']))}</small></td>"
                f"<td><span class='market'>{escape(str(row['market']))}</span>"
                f"<strong>{escape(str(row['selection']))}</strong>"
                f"<small>{escape(str(row['bookmaker_key']))}</small></td>"
                f"<td class='num'><strong>{self._odd(row['entry_odd'])}</strong>"
                f"<small>observed {escape(self._dt(row['quote_observed_at']))}</small></td>"
                f"<td class='num'><strong>{self._prob(row['model_probability'])}</strong>"
                f"<small>fair {self._prob(row['market_fair_probability'])}</small></td>"
                f"<td class='num'><strong>{self._pct(row['edge'])}</strong>"
                f"<small>EV {self._pct(row['expected_value'])}</small></td>"
                f"<td><strong>{escape(self._dt(row['blocked_at']))}</strong>"
                f"<small>{escape(str(row['blocked_stage']))} · {escape(str(row['capture_method']))}</small></td>"
                f"<td class='num'><strong>{self._odd(row['closing_odd'])}</strong>"
                f"<small>CLV {self._clv(row['clv_ppm'])}"
                f"{'' if close_age is None else ' · age ' + str(close_age) + 's'}</small></td>"
                f"<td><span class='status {outcome.lower()}'>{escape(outcome)}</span>"
                f"<small>{escape(str(row.get('regulation_home_goals') if row.get('regulation_home_goals') is not None else '—'))}"
                f"–{escape(str(row.get('regulation_away_goals') if row.get('regulation_away_goals') is not None else '—'))}</small></td>"
                f"<td class='num'><strong>{'—' if pnl is None else f'{Decimal(pnl):+.3f}u'}</strong></td>"
                "</tr>"
            )
        if not rows_html:
            rows_html.append("<tr><td colspan='10' class='empty'>No research signals yet.</td></tr>")

        bucket_html = []
        for row in data["bucket_rows"]:
            bucket_html.append(
                "<tr>"
                f"<td><strong>{escape(row['bucket'])}</strong></td>"
                f"<td class='num'>{row['signals']}</td>"
                f"<td class='num'>{row['settled']}</td>"
                f"<td class='num'>{'—' if row['hit_rate'] is None else f'{row['hit_rate']*100:.1f}%'}</td>"
                f"<td class='num'>{self._roi(row['unit_roi'])}</td>"
                f"<td class='num'>{self._clv(row['avg_clv_ppm'])}</td>"
                "</tr>"
            )

        avg_clv = self._clv(summary["average_clv_ppm"])
        positive = (
            "—"
            if summary["positive_clv_rate"] is None
            else f"{summary['positive_clv_rate'] * 100:.1f}%"
        )
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>QuantBet Research</title>
<style>
:root{{--bg:#090c12;--panel:#111722;--panel2:#161e2b;--line:#253044;--text:#e7edf7;--muted:#8592a6;--green:#36d399;--red:#fb7185;--amber:#f5b942;--blue:#4e8cff}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 Inter,ui-sans-serif,system-ui,sans-serif}}
main{{max-width:1900px;margin:auto;padding:24px}}h1{{margin:3px 0;font-size:28px}}.eyebrow{{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}}
.muted,small{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(6,1fr);gap:9px;margin:18px 0}}
.card,.panel{{background:var(--panel);border:1px solid var(--line)}}.card{{padding:13px}}.card span{{display:block;color:var(--muted)}}.card strong{{display:block;font-size:20px;margin-top:5px}}
.panel{{margin-top:12px}}.head{{padding:12px 14px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between}}.table{{overflow:auto}}
table{{border-collapse:collapse;width:100%;min-width:1450px}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:middle}}th{{background:var(--panel2);color:var(--muted);font-size:10px;text-transform:uppercase;text-align:left;position:sticky;top:0}}
td small{{display:block;margin-top:3px}}.num{{text-align:right;font-variant-numeric:tabular-nums}}.market{{display:block;color:var(--muted);font-size:10px}}code{{color:#a9c5ff}}
.status{{border:1px solid var(--line);padding:3px 6px;font-size:9px;font-weight:800}}.status.win{{color:var(--green)}}.status.loss{{color:var(--red)}}.status.void{{color:var(--muted)}}.status.pending{{color:var(--amber)}}.status.correction{{color:var(--red)}}.empty{{text-align:center;padding:30px}}
.bucket table{{min-width:700px}}@media(max-width:1000px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<div class="eyebrow">QuantBet / Shadow Research</div><h1>Exposure-blocked signal lab</h1>
<div class="muted">No bankroll reservations. No operator actions. Durable research over signals blocked only by open exposure.</div>
<section class="cards">
<div class="card"><span>Raw signals</span><strong>{summary['raw_signals']}</strong></div>
<div class="card"><span>Unique fixtures</span><strong>{summary['unique_fixtures']}</strong></div>
<div class="card"><span>Settled first-per-fixture</span><strong>{summary['settled_primary']}</strong></div>
<div class="card"><span>1-unit ROI</span><strong>{self._roi(summary['unit_roi'])}</strong></div>
<div class="card"><span>Average CLV</span><strong>{avg_clv}</strong></div>
<div class="card"><span>Positive CLV rate</span><strong>{positive}</strong></div>
</section>
<section class="panel bucket"><div class="head"><strong>Model-probability buckets</strong><span class="muted">first blocked signal per fixture</span></div>
<div class="table"><table><thead><tr><th>Model p</th><th class="num">Signals</th><th class="num">Settled</th><th class="num">Hit rate</th><th class="num">1u ROI</th><th class="num">Avg CLV</th></tr></thead>
<tbody>{''.join(bucket_html)}</tbody></table></div></section>
<section class="panel"><div class="head"><strong>All exposure-blocked signals</strong><span class="muted">raw immutable evaluations</span></div>
<div class="table"><table><thead><tr><th>ID</th><th>Fixture</th><th>Signal</th><th class="num">Entry</th><th class="num">Probability</th><th class="num">Value</th><th>Blocked</th><th class="num">Closing</th><th>Result</th><th class="num">1u P/L</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table></div></section>
</main></body></html>"""


class ResearchDashboardHTTPService:
    def __init__(
        self, dashboard: ResearchDashboardService, *, host: str, port: int
    ) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                path = parsed.path
                if path == "/livez":
                    service._json(self, 200, {"live": True})
                    return
                if path in {"/", "/research"}:
                    if service._authorize(self):
                        try:
                            service._html(self, 200, dashboard.render_html())
                        except Exception as exc:  # noqa: BLE001
                            service._json(self, 503, {"error": type(exc).__name__})
                    return
                if path == "/api/research-signals":
                    if service._authorize(self):
                        try:
                            values = parse_qs(parsed.query)
                            fixture_id = values.get("provider_fixture_id", [None])[0]
                            data = dashboard.snapshot(provider_fixture_id=fixture_id)
                            service._json(
                                self,
                                200,
                                {
                                    "generated_at": _json_safe(data["generated_at"]),
                                    "summary": _json_safe(data["summary"]),
                                    "rows": _json_safe(data["rows"]),
                                },
                            )
                        except Exception as exc:  # noqa: BLE001
                            service._json(self, 503, {"error": type(exc).__name__})
                    return
                service._json(self, 404, {"error": "not_found"})

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @staticmethod
    def _json(handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(_json_safe(body), separators=(",", ":")).encode()
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
        handler.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    def _authorize(self, handler: BaseHTTPRequestHandler) -> bool:
        if dashboard_is_public():
            return True
        password = os.environ.get("QUANTBET_DASHBOARD_PASSWORD", "")
        username = os.environ.get("QUANTBET_DASHBOARD_USER", "quantbet")
        if not password:
            self._json(handler, 404, {"error": "not_found"})
            return False
        supplied_user = supplied_password = ""
        authorization = handler.headers.get("Authorization", "")
        if authorization.startswith("Basic "):
            try:
                decoded = base64.b64decode(authorization[6:], validate=True).decode()
                supplied_user, supplied_password = decoded.split(":", 1)
            except (ValueError, UnicodeDecodeError):
                pass
        if hmac.compare_digest(supplied_user, username) and hmac.compare_digest(
            supplied_password, password
        ):
            return True
        encoded = b'{"error":"authentication_required"}'
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="QuantBet Research"')
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
