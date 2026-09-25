"""Read-only research dashboard for bankroll-neutral exposure-blocked signals."""

from __future__ import annotations

import base64
import hmac
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlsplit


def _connect(database_url: str) -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL support requires psycopg[binary]") from exc
    return psycopg.connect(database_url)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required research dashboard configuration: {name}")
    return value


def _public() -> bool:
    value = os.getenv(
        "QUANTBET_RESEARCH_DASHBOARD_PUBLIC",
        os.getenv("QUANTBET_DASHBOARD_PUBLIC", ""),
    )
    return value.strip().lower() in {"1", "true", "yes"}


def _auth_value(name: str) -> str:
    specific = os.getenv(f"QUANTBET_RESEARCH_DASHBOARD_{name}", "").strip()
    if specific:
        return specific
    return os.getenv(f"QUANTBET_DASHBOARD_{name}", "").strip()


class ResearchDashboardService:
    """Project durable research facts without bankroll or provider mutations."""

    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be blank")
        self._database_url = database_url

    def rows(self, *, provider_fixture_id: str | None = None) -> list[dict[str, Any]]:
        sql = """
            WITH latest_fixture AS (
                SELECT DISTINCT ON (fo.fixture_id)
                    fo.fixture_id, fo.home_team, fo.away_team, fo.competition_name,
                    fo.country, fo.competition_type, fo.kickoff_at, fo.provider_status
                FROM fixture_observations fo
                ORDER BY fo.fixture_id, fo.observed_at DESC, fo.fixture_observation_id DESC
            )
            SELECT
                signal.evaluation_id,
                signal.first_blocked_at,
                signal.last_blocked_at,
                signal.block_count,
                signal.first_open_exposure_minor,
                signal.last_open_exposure_minor,
                signal.max_open_exposure_minor,
                signal.fixed_stake_minor,
                signal.capture_origin,
                e.fixture_id,
                f.provider_fixture_id,
                f.league_id,
                f.season,
                latest.home_team,
                latest.away_team,
                latest.competition_name,
                latest.country,
                latest.kickoff_at,
                latest.provider_status,
                e.market,
                e.selected_selection AS selection,
                e.bookmaker_id,
                e.bookmaker_key,
                e.source,
                e.selected_odd AS signal_odd,
                e.companion_odd,
                e.quote_observed_at,
                e.selected_captured_at,
                e.model_probability,
                e.selected_devig_probability AS market_fair_probability,
                e.edge,
                e.expected_value,
                e.model_version_id,
                prediction.prediction_method_version,
                close_quote.odd AS observed_closing_odd,
                close_quote.observed_at AS observed_closing_at,
                result_state.phase AS result_phase,
                result.provider_status AS result_provider_status,
                result.regulation_home_goals,
                result.regulation_away_goals,
                result.result_classification,
                EXISTS (
                    SELECT 1
                    FROM registered_picks rp
                    WHERE rp.fixture_id = e.fixture_id
                      AND rp.market = e.market
                      AND rp.selection = e.selected_selection
                      AND rp.registered_at >= signal.first_blocked_at
                ) AS eventually_registered
            FROM research_exposure_signals signal
            JOIN value_evaluations e
              ON e.evaluation_id = signal.evaluation_id
            JOIN fixtures f
              ON f.fixture_id = e.fixture_id
            JOIN fixture_predictions prediction
              ON prediction.prediction_id = e.prediction_id
            LEFT JOIN latest_fixture latest
              ON latest.fixture_id = e.fixture_id
            LEFT JOIN LATERAL (
                SELECT q.odd, q.observed_at
                FROM quote_snapshots q
                WHERE q.series_id = e.selected_series_id
                  AND q.source = e.source
                  AND q.observed_at < latest.kickoff_at
                  AND q.captured_at < latest.kickoff_at
                  AND q.captured_at >= e.selected_captured_at
                ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC
                LIMIT 1
            ) close_quote ON TRUE
            LEFT JOIN fixture_result_acquisition_states result_state
              ON result_state.fixture_id = e.fixture_id
            LEFT JOIN fixture_result_observations result
              ON result.result_observation_id = CASE
                    WHEN result_state.phase IN ('POST_SETTLEMENT_RECHECK', 'COMPLETE')
                    THEN COALESCE(
                        result_state.candidate_observation_id,
                        result_state.current_observation_id
                    )
                    ELSE NULL
                 END
            WHERE (%s IS NULL OR f.provider_fixture_id = %s)
            ORDER BY signal.first_blocked_at DESC, signal.evaluation_id DESC
            LIMIT 10000
        """
        with _connect(self._database_url) as connection, connection.cursor() as cursor:
            cursor.execute(sql, (provider_fixture_id, provider_fixture_id))
            columns = [item.name for item in cursor.description]
            values = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        for row in values:
            self._derive(row)
        return values

    @staticmethod
    def _derive(row: dict[str, Any]) -> None:
        closing = row.get("observed_closing_odd")
        entry = row.get("signal_odd")
        if closing is not None and entry is not None and float(closing) > 1:
            row["research_clv"] = float(entry) / float(closing) - 1.0
        else:
            row["research_clv"] = None

        classification = row.get("result_classification")
        home = row.get("regulation_home_goals")
        away = row.get("regulation_away_goals")
        if classification == "NON_PLAYED_VOIDABLE":
            outcome = "VOID"
        elif classification == "PLAYED_SETTLEABLE" and home is not None and away is not None:
            total = int(home) + int(away)
            market = row.get("market")
            selection = row.get("selection")
            if market == "OU_25" and selection == "OVER":
                won = total >= 3
            elif market == "OU_25" and selection == "UNDER":
                won = total <= 2
            elif market == "BTTS" and selection == "YES":
                won = int(home) >= 1 and int(away) >= 1
            elif market == "BTTS" and selection == "NO":
                won = int(home) == 0 or int(away) == 0
            else:
                won = None
            outcome = None if won is None else ("WIN" if won else "LOSS")
        else:
            outcome = None
        row["counterfactual_outcome"] = outcome
        if outcome == "WIN":
            row["counterfactual_units"] = float(row["signal_odd"]) - 1.0
        elif outcome == "LOSS":
            row["counterfactual_units"] = -1.0
        elif outcome == "VOID":
            row["counterfactual_units"] = 0.0
        else:
            row["counterfactual_units"] = None

    @staticmethod
    def _probability_bucket(value: float) -> str:
        percent = value * 100.0
        for lower in (40, 45, 50, 55, 60, 65, 70, 75):
            upper = lower + 5
            if lower <= percent < upper:
                return f"{lower}–{upper}%"
        return "<40%" if percent < 40 else "80%+"

    @staticmethod
    def _ev_bucket(value: float) -> str:
        percent = value * 100.0
        if percent < 10:
            return "7–10%"
        if percent < 15:
            return "10–15%"
        if percent < 20:
            return "15–20%"
        if percent < 30:
            return "20–30%"
        return "30%+"

    @staticmethod
    def _bucket(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row[key])].append(row)
        result = []
        for label, items in grouped.items():
            resolved = [
                item for item in items
                if item.get("counterfactual_outcome") in {"WIN", "LOSS", "VOID"}
            ]
            decided = [
                item for item in resolved
                if item.get("counterfactual_outcome") in {"WIN", "LOSS"}
            ]
            wins = sum(item.get("counterfactual_outcome") == "WIN" for item in decided)
            clv = [
                float(item["research_clv"])
                for item in items if item.get("research_clv") is not None
            ]
            units = [
                float(item["counterfactual_units"])
                for item in resolved if item.get("counterfactual_units") is not None
            ]
            result.append(
                {
                    "bucket": label,
                    "signals": len(items),
                    "fixtures": len({item["fixture_id"] for item in items}),
                    "resolved": len(resolved),
                    "hit_rate": None if not decided else wins / len(decided),
                    "avg_model_probability": sum(float(item["model_probability"]) for item in items) / len(items),
                    "avg_ev": sum(float(item["expected_value"]) for item in items) / len(items),
                    "avg_clv": None if not clv else sum(clv) / len(clv),
                    "flat_yield": None if not units else sum(units) / len(units),
                }
            )
        return result

    def snapshot(self, *, provider_fixture_id: str | None = None) -> dict[str, Any]:
        rows = self.rows(provider_fixture_id=provider_fixture_id)
        for row in rows:
            row["probability_bucket"] = self._probability_bucket(float(row["model_probability"]))
            row["ev_bucket"] = self._ev_bucket(float(row["expected_value"]))
        resolved = [row for row in rows if row.get("counterfactual_outcome") is not None]
        clv = [float(row["research_clv"]) for row in rows if row.get("research_clv") is not None]
        units = [
            float(row["counterfactual_units"])
            for row in resolved if row.get("counterfactual_units") is not None
        ]
        return {
            "generated_at": datetime.now(UTC),
            "filter_provider_fixture_id": provider_fixture_id,
            "rows": rows,
            "counts": {
                "signals": len(rows),
                "fixtures": len({row["fixture_id"] for row in rows}),
                "resolved": len(resolved),
                "pending": len(rows) - len(resolved),
                "eventually_registered": sum(bool(row["eventually_registered"]) for row in rows),
            },
            "averages": {
                "ev": None if not rows else sum(float(row["expected_value"]) for row in rows) / len(rows),
                "clv": None if not clv else sum(clv) / len(clv),
                "flat_yield": None if not units else sum(units) / len(units),
            },
            "probability_buckets": self._bucket(rows, "probability_bucket"),
            "ev_buckets": self._bucket(rows, "ev_bucket"),
        }

    @staticmethod
    def _pct(value: Any) -> str:
        return "—" if value is None else f"{float(value) * 100:+.2f}%"

    @staticmethod
    def _prob(value: Any) -> str:
        return "—" if value is None else f"{float(value) * 100:.2f}%"

    @staticmethod
    def _odd(value: Any) -> str:
        return "—" if value is None else f"{float(value):.2f}"

    @staticmethod
    def _dt(value: Any) -> str:
        if value is None:
            return "—"
        return value.astimezone(UTC).strftime("%d %b %Y · %H:%M UTC")

    @staticmethod
    def _units(value: Any) -> str:
        return "—" if value is None else f"{float(value):+.2f}u"

    def _bucket_table(self, rows: list[dict[str, Any]], title: str) -> str:
        body = ""
        for row in rows:
            body += (
                "<tr>"
                f"<td><strong>{escape(str(row['bucket']))}</strong></td>"
                f"<td class='num'>{row['signals']}</td>"
                f"<td class='num'>{row['fixtures']}</td>"
                f"<td class='num'>{row['resolved']}</td>"
                f"<td class='num'>{escape(self._prob(row['hit_rate']))}</td>"
                f"<td class='num'>{escape(self._prob(row['avg_model_probability']))}</td>"
                f"<td class='num'>{escape(self._pct(row['avg_ev']))}</td>"
                f"<td class='num'>{escape(self._pct(row['avg_clv']))}</td>"
                f"<td class='num'>{escape(self._pct(row['flat_yield']))}</td>"
                "</tr>"
            )
        if not body:
            body = "<tr><td colspan='9' class='empty'>No research signals yet.</td></tr>"
        return (
            f"<section class='panel'><div class='panel-head'><h2>{escape(title)}</h2></div>"
            "<div class='table-wrap'><table class='bucket'><thead><tr>"
            "<th>Bucket</th><th>Signals</th><th>Fixtures</th><th>Resolved</th>"
            "<th>Hit rate</th><th>Avg model p</th><th>Avg EV</th><th>Avg CLV</th>"
            "<th>Flat yield</th></tr></thead><tbody>"
            f"{body}</tbody></table></div></section>"
        )

    def render_html(self, *, provider_fixture_id: str | None = None) -> str:
        data = self.snapshot(provider_fixture_id=provider_fixture_id)
        counts = data["counts"]
        averages = data["averages"]
        rows_html = ""
        for row in data["rows"]:
            score = (
                "—"
                if row.get("regulation_home_goals") is None
                else f"{row['regulation_home_goals']}–{row['regulation_away_goals']}"
            )
            outcome = row.get("counterfactual_outcome") or "PENDING"
            outcome_css = str(outcome).casefold()
            eventually = "YES" if row.get("eventually_registered") else "NO"
            rows_html += (
                "<tr>"
                f"<td><code>{escape(str(row['provider_fixture_id']))}</code>"
                f"<small>{escape(str(row['fixture_id']))}</small></td>"
                f"<td class='fixture'><strong>{escape(str(row.get('home_team') or '—'))} – "
                f"{escape(str(row.get('away_team') or '—'))}</strong>"
                f"<small>{escape(str(row.get('competition_name') or '—'))} · "
                f"{escape(self._dt(row.get('kickoff_at')))}</small></td>"
                f"<td><span class='market'>{escape(str(row['market']))}</span>"
                f"<strong>{escape(str(row['selection']))}</strong>"
                f"<small>{escape(str(row['bookmaker_key']))}</small></td>"
                f"<td class='num'><strong>{self._odd(row['signal_odd'])}</strong>"
                f"<small>observed {escape(self._dt(row['quote_observed_at']))}</small></td>"
                f"<td class='num'><strong>{self._prob(row['model_probability'])}</strong>"
                f"<small>fair {self._prob(row['market_fair_probability'])}</small></td>"
                f"<td class='num'><strong>{self._pct(row['edge'])}</strong>"
                f"<small>EV {self._pct(row['expected_value'])}</small></td>"
                f"<td class='num'><strong>{self._odd(row['observed_closing_odd'])}</strong>"
                f"<small>{escape(self._dt(row['observed_closing_at']))}</small></td>"
                f"<td class='num'><strong>{self._pct(row['research_clv'])}</strong></td>"
                f"<td><span class='status {escape(outcome_css)}'>{escape(str(outcome))}</span>"
                f"<small>{escape(score)} · {escape(self._units(row['counterfactual_units']))}</small></td>"
                f"<td class='num'><strong>{row['block_count']}</strong>"
                f"<small>{escape(str(row['capture_origin']))}</small></td>"
                f"<td><strong>{eventually}</strong></td>"
                "</tr>"
            )
        if not rows_html:
            rows_html = "<tr><td colspan='11' class='empty'>No matching exposure-blocked signals.</td></tr>"

        filter_value = escape(provider_fixture_id or "")
        prob_table = self._bucket_table(data["probability_buckets"], "Model probability buckets")
        ev_table = self._bucket_table(data["ev_buckets"], "Expected-value buckets")
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>QuantBet · Research</title>
<style>
:root{{--bg:#090c12;--panel:#111722;--panel2:#161e2b;--line:#253044;--text:#e7edf7;
--muted:#8592a6;--blue:#4e8cff;--green:#36d399;--red:#fb7185;--amber:#f5b942}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px/1.45
Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}.shell{{max-width:1900px;margin:auto;padding:24px}}
header{{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:18px}}
.eyebrow{{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.13em;text-transform:uppercase}}
h1{{margin:3px 0;font-size:27px}}.muted,small{{color:var(--muted)}}.kpis{{display:grid;
grid-template-columns:repeat(7,minmax(130px,1fr));gap:8px;margin-bottom:12px}}.kpi,.panel{{
background:var(--panel);border:1px solid var(--line)}}.kpi{{padding:12px}}.kpi span{{display:block;color:var(--muted);
font-size:10px}}.kpi strong{{display:block;font-size:18px;margin-top:5px}}.panel{{margin-top:12px}}
.panel-head{{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-bottom:1px solid var(--line)}}
h2{{font-size:14px;margin:0}}form{{display:flex;gap:6px}}input{{background:var(--panel2);color:var(--text);
border:1px solid var(--line);padding:7px 9px}}button,a.button{{background:var(--blue);color:#fff;border:0;
padding:7px 10px;text-decoration:none}}.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:1500px}}
table.bucket{{min-width:900px}}th,td{{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;
vertical-align:middle}}th{{background:var(--panel2);color:var(--muted);font-size:9px;letter-spacing:.08em;
text-transform:uppercase;position:sticky;top:0}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.fixture{{min-width:260px}}.market{{display:block;color:var(--muted);font-size:9px}}code{{color:#a9c5ff}}
.status{{display:inline-block;padding:3px 6px;border:1px solid var(--line);font-size:9px;font-weight:800}}
.status.win{{color:var(--green);border-color:#1f6a51}}.status.loss{{color:var(--red);border-color:#6f2c3a}}
.status.void{{color:var(--amber)}}.status.pending{{color:#8ab4ff}}.empty{{text-align:center;padding:30px;color:var(--muted)}}
.note{{padding:12px 14px;color:var(--muted)}}@media(max-width:900px){{.kpis{{grid-template-columns:repeat(2,1fr)}}
.shell{{padding:12px}}header{{align-items:start;flex-direction:column}}}}
</style></head><body><main class="shell">
<header><div><div class="eyebrow">QuantBet / Shadow Research</div><h1>Exposure-blocked signals</h1>
<div class="muted">Bankroll-neutral · durable PostgreSQL research ledger</div></div>
<form method="get" action="/research"><input name="fixture" inputmode="numeric" placeholder="API-Football fixture ID"
value="{filter_value}"><button type="submit">Find fixture</button>
<a class="button" href="/research">Clear</a></form></header>
<section class="kpis">
<article class="kpi"><span>Signals</span><strong>{counts['signals']}</strong></article>
<article class="kpi"><span>Unique fixtures</span><strong>{counts['fixtures']}</strong></article>
<article class="kpi"><span>Resolved</span><strong>{counts['resolved']}</strong></article>
<article class="kpi"><span>Pending</span><strong>{counts['pending']}</strong></article>
<article class="kpi"><span>Avg EV</span><strong>{escape(self._pct(averages['ev']))}</strong></article>
<article class="kpi"><span>Avg research CLV</span><strong>{escape(self._pct(averages['clv']))}</strong></article>
<article class="kpi"><span>Flat 1u yield</span><strong>{escape(self._pct(averages['flat_yield']))}</strong></article>
</section>
<div class="note">Research CLV uses the latest stored pre-kickoff quote from the same selected quote series.
These are preliminary exposure-blocked signals: they did not receive the mandatory final quote refresh,
so they are research observations, not guaranteed would-have-been registered picks. Bucket rows are not
statistically independent because one fixture can generate multiple quote observations.</div>
{prob_table}{ev_table}
<section class="panel"><div class="panel-head"><h2>Signal ledger</h2>
<span class="muted">{counts['eventually_registered']} later matched a registered fixture/selection</span></div>
<div class="table-wrap"><table><thead><tr>
<th>Fixture ID</th><th>Match</th><th>Signal</th><th class="num">Odds</th>
<th class="num">Probability</th><th class="num">Value</th><th class="num">Observed close</th>
<th class="num">Research CLV</th><th>Outcome</th><th class="num">Blocks</th><th>Later registered</th>
</tr></thead><tbody>{rows_html}</tbody></table></div></section>
</main></body></html>"""

    @staticmethod
    def json_payload(data: dict[str, Any]) -> bytes:
        def default(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.astimezone(UTC).isoformat()
            if isinstance(value, Decimal):
                return str(value)
            raise TypeError(type(value).__name__)
        return json.dumps(data, default=default, separators=(",", ":")).encode("utf-8")


class ResearchDashboardHTTPService:
    def __init__(self, dashboard: ResearchDashboardService, *, host: str, port: int) -> None:
        self._dashboard = dashboard
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path == "/livez":
                    service._json(self, 200, {"live": True})
                    return
                if parsed.path not in {"/", "/research", "/api/research-signals"}:
                    service._json(self, 404, {"error": "not_found"})
                    return
                if not service._authorize(self):
                    return
                fixture = parse_qs(parsed.query).get("fixture", [None])[0]
                if fixture is not None:
                    fixture = fixture.strip() or None
                    if fixture is not None and not fixture.isdigit():
                        service._json(self, 400, {"error": "fixture_must_be_numeric"})
                        return
                try:
                    if parsed.path == "/api/research-signals":
                        service._raw_json(
                            self,
                            200,
                            dashboard.json_payload(
                                dashboard.snapshot(provider_fixture_id=fixture)
                            ),
                        )
                    else:
                        service._html(
                            self,
                            200,
                            dashboard.render_html(provider_fixture_id=fixture),
                        )
                except Exception as exc:  # noqa: BLE001
                    service._json(self, 503, {"error": type(exc).__name__})

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread: Thread | None = None

    def _authorize(self, handler: BaseHTTPRequestHandler) -> bool:
        if _public():
            return True
        user = _auth_value("USER")
        password = _auth_value("PASSWORD")
        if not user or not password:
            self._json(handler, 404, {"error": "not_found"})
            return False
        header = handler.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            self._auth_required(handler)
            return False
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
            supplied_user, supplied_password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            self._auth_required(handler)
            return False
        if not (
            hmac.compare_digest(supplied_user, user)
            and hmac.compare_digest(supplied_password, password)
        ):
            self._auth_required(handler)
            return False
        return True

    @staticmethod
    def _auth_required(handler: BaseHTTPRequestHandler) -> None:
        body = b'{"error":"authentication_required"}'
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="QuantBet Research"')
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    @staticmethod
    def _raw_json(handler: BaseHTTPRequestHandler, status: int, body: bytes) -> None:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    @classmethod
    def _json(cls, handler: BaseHTTPRequestHandler, status: int, value: dict[str, Any]) -> None:
        cls._raw_json(handler, status, json.dumps(value).encode("utf-8"))

    @staticmethod
    def _html(handler: BaseHTTPRequestHandler, status: int, value: str) -> None:
        body = value.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def build_research_dashboard_from_environment() -> ResearchDashboardService:
    return ResearchDashboardService(_required("DATABASE_URL"))
