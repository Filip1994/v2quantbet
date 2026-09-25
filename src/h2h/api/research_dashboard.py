"""Read-only dashboard for QuantBet shadow/research signals."""

from __future__ import annotations

import base64
import hmac
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from h2h.domain.settlement import realized_clv_ppm
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository


BELGRADE = ZoneInfo("Europe/Belgrade")


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _pct(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number * 100:.1f}%"


def _odd(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.2f}"


def _time(value: Any) -> str:
    if not isinstance(value, datetime):
        return "—"
    return value.astimezone(BELGRADE).strftime("%Y-%m-%d %H:%M")


def _probability_bucket(value: Any) -> str:
    p = _number(value)
    if p is None:
        return "—"
    pct = p * 100
    for low, high in ((40, 45), (45, 50), (50, 55), (55, 60), (60, 65), (65, 70), (70, 75)):
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 75:
        return "75%+"
    return "<40%"


def _ev_bucket(value: Any) -> str:
    ev = _number(value)
    if ev is None:
        return "—"
    pct = ev * 100
    for low, high in ((7, 10), (10, 15), (15, 20), (20, 30)):
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 30:
        return "30%+"
    return "<7%"


def _odds_bucket(value: Any) -> str:
    odds = _number(value)
    if odds is None:
        return "—"
    for low, high, label in (
        (1.40, 1.60, "1.40–1.60"),
        (1.60, 1.80, "1.61–1.80"),
        (1.80, 2.00, "1.81–2.00"),
        (2.00, 2.50, "2.01–2.50"),
        (2.50, 3.00, "2.51–3.00"),
        (3.00, 3.50, "3.01–3.50"),
    ):
        if low <= odds <= high:
            return label
    return "other"


def counterfactual_outcome(row: dict[str, Any]) -> str:
    classification = row.get("result_classification")
    if classification == "NON_PLAYED_VOIDABLE":
        return "VOID"
    if classification != "PLAYED_SETTLEABLE":
        return "PENDING"
    home = row.get("regulation_home_goals")
    away = row.get("regulation_away_goals")
    if home is None or away is None:
        return "PENDING"
    home, away = int(home), int(away)
    market, selection = row.get("market"), row.get("selection")
    if market == "OU_25":
        over = home + away > 2
        won = over if selection == "OVER" else not over
    elif market == "BTTS":
        yes = home > 0 and away > 0
        won = yes if selection == "YES" else not yes
    else:
        return "PENDING"
    return "WIN" if won else "LOSS"


def counterfactual_pnl_minor(row: dict[str, Any], stake_minor: int) -> int | None:
    outcome = counterfactual_outcome(row)
    if outcome == "PENDING":
        return None
    if outcome == "VOID":
        return 0
    if outcome == "LOSS":
        return -stake_minor
    odd = Decimal(str(row["odds"]))
    return int(
        (Decimal(stake_minor) * (odd - Decimal(1))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )


def research_clv_ppm(row: dict[str, Any]) -> int | None:
    closing = row.get("closing_odds")
    closing_at = row.get("closing_observed_at")
    entry_at = row.get("quote_observed_at")
    if closing is None or not isinstance(closing_at, datetime) or not isinstance(entry_at, datetime):
        return None
    if closing_at <= entry_at:
        return None
    return realized_clv_ppm(Decimal(str(row["odds"])), Decimal(str(closing)))


def _parse_fraction(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    value = float(raw)
    return value / 100 if abs(value) > 1 else value


def _parse_float(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    return float(raw)


def _one_signal_per_fixture(
    rows: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Project historical shadow rows onto the production one-pick-per-fixture rule."""

    def strength(row: dict[str, Any], name: str) -> float:
        value = _number(row.get(name))
        return float("-inf") if value is None else value

    chosen: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
    for row in rows:
        fixture_id = str(row["fixture_id"])
        first_blocked_at = row["first_blocked_at"]
        if not isinstance(first_blocked_at, datetime):
            raise TypeError("first_blocked_at must be a datetime")

        rank = (
            first_blocked_at,
            -strength(row, "expected_value"),
            -strength(row, "edge"),
            -strength(row, "odds"),
            str(row["evaluation_id"]),
        )
        current = chosen.get(fixture_id)
        if current is None or rank < current[0]:
            chosen[fixture_id] = (rank, row)

    return tuple(
        sorted(
            (item[1] for item in chosen.values()),
            key=lambda row: (row["last_blocked_at"], str(row["evaluation_id"])),
            reverse=True,
        )
    )


class ResearchDashboardService:
    def __init__(
        self,
        repository: PostgreSQLResearchSignalRepository,
        *,
        fixed_stake_minor: int = 30_000,
        strict_quote_age_seconds: int = 300,
        provider_snapshot_max_age_seconds: int = 28_800,
    ) -> None:
        self._repository = repository
        self._stake = fixed_stake_minor
        self._strict_age = strict_quote_age_seconds
        self._provider_age = provider_snapshot_max_age_seconds

    def _derived(self, row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        quote_age = max(
            0,
            int((item["first_blocked_at"] - item["quote_observed_at"]).total_seconds()),
        )
        item["quote_age_seconds"] = quote_age
        item["freshness"] = (
            "FRESH"
            if quote_age <= self._strict_age
            else "USABLE_STALE"
            if quote_age <= self._provider_age
            else "HARD_STALE"
        )
        item["outcome"] = counterfactual_outcome(item)
        item["pnl_minor"] = counterfactual_pnl_minor(item, self._stake)
        item["clv_ppm"] = research_clv_ppm(item)
        item["probability_bucket"] = _probability_bucket(item["model_probability"])
        item["ev_bucket"] = _ev_bucket(item["expected_value"])
        item["odds_bucket"] = _odds_bucket(item["odds"])
        return item

    def signals(self, params: dict[str, list[str]]) -> tuple[dict[str, Any], ...]:
        canonical = _one_signal_per_fixture(self._repository.list_signals(limit=5000))
        rows = tuple(self._derived(row) for row in canonical)
        market = params.get("market", [""])[0].strip().upper()
        league = params.get("league", [""])[0].strip().casefold()
        result = params.get("result", [""])[0].strip().upper()
        p_min = _parse_fraction(params.get("p_min", [""])[0])
        p_max = _parse_fraction(params.get("p_max", [""])[0])
        ev_min = _parse_fraction(params.get("ev_min", [""])[0])
        ev_max = _parse_fraction(params.get("ev_max", [""])[0])
        odds_min = _parse_float(params.get("odds_min", [""])[0])
        odds_max = _parse_float(params.get("odds_max", [""])[0])

        def keep(row: dict[str, Any]) -> bool:
            p, ev, odds = (
                float(row["model_probability"]),
                float(row["expected_value"]),
                float(row["odds"]),
            )
            if market and row["market"].upper() != market:
                return False
            if league and league not in (row.get("competition_name") or "").casefold():
                return False
            if result and row["outcome"] != result:
                return False
            if p_min is not None and p < p_min:
                return False
            if p_max is not None and p > p_max:
                return False
            if ev_min is not None and ev < ev_min:
                return False
            if ev_max is not None and ev > ev_max:
                return False
            if odds_min is not None and odds < odds_min:
                return False
            return not (odds_max is not None and odds > odds_max)

        return tuple(row for row in rows if keep(row))

    def render_html(self, query: str = "") -> str:
        params = parse_qs(query, keep_blank_values=True)
        rows = self.signals(params)
        settled = [row for row in rows if row["outcome"] != "PENDING"]
        clvs = [row["clv_ppm"] for row in rows if row["clv_ppm"] is not None]
        pnl = sum(row["pnl_minor"] or 0 for row in settled)
        unique_fixtures = len({row["fixture_id"] for row in rows})
        avg_clv = (sum(clvs) / len(clvs) / 10_000) if clvs else None

        def field(name: str) -> str:
            return escape(params.get(name, [""])[0], quote=True)

        body_rows = []
        for row in rows:
            clv = "—" if row["clv_ppm"] is None else f'{row["clv_ppm"] / 10_000:+.2f}%'
            pnl_rsd = "—" if row["pnl_minor"] is None else f'{row["pnl_minor"] / 100:+.0f}'
            exposure = f'{row["last_open_exposure_minor"] / 100:.0f}/{row["exposure_cap_minor"] / 100:.0f}'
            match = f'{escape(row["home_team"])} – {escape(row["away_team"])}'
            competition = escape(row.get("competition_name") or "—")
            body_rows.append(
                "<tr>"
                f'<td><b>{match}</b><small>{competition} · fixture {escape(str(row["provider_fixture_id"]))}</small></td>'
                f'<td>{_time(row["kickoff_at"])}</td>'
                f'<td>{escape(row["market"])} {escape(row["selection"])}</td>'
                f'<td>{_pct(row["model_probability"])}<small>{escape(row["probability_bucket"])}</small></td>'
                f'<td>{_pct(row["market_fair_probability"])}</td>'
                f'<td>{_odd(row["odds"])}<small>{escape(row["odds_bucket"])}</small></td>'
                f'<td>{_pct(row["edge"])}</td>'
                f'<td>{_pct(row["expected_value"])}<small>{escape(row["ev_bucket"])}</small></td>'
                f'<td>{_time(row["first_blocked_at"])}<small>{row["quote_age_seconds"]}s · {escape(row["freshness"])}</small></td>'
                f'<td>{escape(row["bookmaker"])}<small>{escape(row["source"])}</small></td>'
                f'<td>{exposure} RSD<small>x{row["blocked_count"]}</small></td>'
                f'<td>{_odd(row["closing_odds"])}<small>{_time(row["closing_observed_at"])}</small></td>'
                f'<td>{clv}</td>'
                f'<td><b>{escape(row["outcome"])}</b><small>{pnl_rsd} RSD · {escape(row.get("result_phase") or "waiting")}</small></td>'
                "</tr>"
            )
        rows_html = "".join(body_rows) or '<tr><td colspan="14">No signals match these filters.</td></tr>'
        avg_clv_text = "—" if avg_clv is None else f"{avg_clv:+.2f}%"
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantBet Research</title><style>
:root{{color-scheme:dark;background:#0b0d10;color:#eef1f4;font-family:Inter,system-ui,sans-serif}}
*{{box-sizing:border-box}}body{{margin:0;padding:24px}}main{{max-width:1900px;margin:auto}}
h1{{margin:0 0 6px}}p{{color:#9ca6b2}}.cards{{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}}
.card{{background:#15191f;border:1px solid #29313a;border-radius:10px;padding:12px 16px;min-width:150px}}
.card b{{display:block;font-size:22px}}form{{display:flex;gap:8px;flex-wrap:wrap;background:#11151a;padding:12px;border-radius:10px;margin-bottom:14px}}
input,select,button{{background:#0b0d10;color:#eef1f4;border:1px solid #394451;border-radius:6px;padding:8px}}
button{{cursor:pointer}}.table{{overflow:auto;border:1px solid #29313a;border-radius:10px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:10px;border-bottom:1px solid #232a32;text-align:left;white-space:nowrap;vertical-align:top}}
th{{position:sticky;top:0;background:#15191f}}small{{display:block;color:#87919d;margin-top:3px}}
footer{{color:#76808b;margin-top:14px;font-size:12px}}a{{color:#d5dce4}}
</style></head><body><main>
<h1>QuantBet Shadow / Research</h1>
<p>Exposure-only preliminary signals, projected to one canonical shadow pick per fixture. Read-only; no bankroll reservation, pick registration, settlement control or worker scheduler.</p>
<div class="cards">
<div class="card"><small>Signals</small><b>{len(rows)}</b></div>
<div class="card"><small>Unique fixtures</small><b>{unique_fixtures}</b></div>
<div class="card"><small>Resolved</small><b>{len(settled)}</b></div>
<div class="card"><small>Flat P/L</small><b>{pnl / 100:+.0f} RSD</b></div>
<div class="card"><small>Avg research CLV</small><b>{avg_clv_text}</b></div>
</div>
<form method="get">
<select name="market"><option value="">All markets</option><option {"selected" if field("market")=="BTTS" else ""}>BTTS</option><option {"selected" if field("market")=="OU_25" else ""}>OU_25</option></select>
<input name="league" placeholder="League contains" value="{field("league")}">
<input name="p_min" placeholder="Model p min %" value="{field("p_min")}">
<input name="p_max" placeholder="Model p max %" value="{field("p_max")}">
<input name="ev_min" placeholder="EV min %" value="{field("ev_min")}">
<input name="ev_max" placeholder="EV max %" value="{field("ev_max")}">
<input name="odds_min" placeholder="Odds min" value="{field("odds_min")}">
<input name="odds_max" placeholder="Odds max" value="{field("odds_max")}">
<select name="result"><option value="">All results</option>{''.join(f'<option {"selected" if field("result")==v else ""}>{v}</option>' for v in ("WIN","LOSS","VOID","PENDING"))}</select>
<button type="submit">Filter</button><a href="/research">Clear</a>
</form>
<div class="table"><table><thead><tr>
<th>Match</th><th>Kickoff</th><th>Market</th><th>Model p</th><th>Market fair p</th><th>Odds</th><th>Edge</th><th>EV</th><th>Detected</th><th>Bookmaker</th><th>Exposure</th><th>Research close</th><th>CLV</th><th>Counterfactual</th>
</tr></thead><tbody>{rows_html}</tbody></table></div>
<footer>Research close = last stored same-series/source pre-kickoff quote. CLV is shown only when that quote is later than the entry quote. Times are Europe/Belgrade.</footer>
</main></body></html>"""


class ResearchDashboardHTTPService:
    def __init__(self, dashboard: ResearchDashboardService, *, host: str, port: int) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path == "/livez":
                    service._text(self, 200, "ok\n", "text/plain; charset=utf-8")
                    return
                if parsed.path not in {"/", "/research"}:
                    service._text(self, 404, "not_found\n", "text/plain; charset=utf-8")
                    return
                if not service._authorize(self):
                    return
                try:
                    service._text(
                        self,
                        200,
                        dashboard.render_html(parsed.query),
                        "text/html; charset=utf-8",
                    )
                except (TypeError, ValueError):
                    service._text(self, 400, "invalid_filter\n", "text/plain; charset=utf-8")
                except Exception as exc:  # noqa: BLE001 - bounded read-only failure response
                    service._text(
                        self, 503, type(exc).__name__ + "\n", "text/plain; charset=utf-8"
                    )

            def do_POST(self) -> None:
                service._text(self, 405, "read_only\n", "text/plain; charset=utf-8")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @staticmethod
    def _text(
        handler: BaseHTTPRequestHandler, status: int, body: str, content_type: str
    ) -> None:
        encoded = body.encode()
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    @staticmethod
    def _authorize(handler: BaseHTTPRequestHandler) -> bool:
        public = os.environ.get("QUANTBET_RESEARCH_PUBLIC", "").strip().casefold()
        if public in {"1", "true", "yes", "on"}:
            return True
        password = os.environ.get("QUANTBET_RESEARCH_PASSWORD", "")
        username = os.environ.get("QUANTBET_RESEARCH_USER", "quantbet")
        if not password:
            ResearchDashboardHTTPService._text(
                handler, 404, "not_found\n", "text/plain; charset=utf-8"
            )
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
        encoded = b'authentication_required\n'
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="QuantBet Research"')
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)
        return False

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
