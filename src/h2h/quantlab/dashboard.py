"""Read-only dashboard for QuantLab multi-market experiments."""

from __future__ import annotations

import base64
import hmac
import os
from datetime import datetime
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from h2h.domain.settlement import realized_clv_ppm
from h2h.quantlab.repository import PostgreSQLQuantLabRepository


BELGRADE = ZoneInfo("Europe/Belgrade")
LABS = {
    "goal": ("GOAL", "GoalLab", "Goals · DC+ and goal-market experiments"),
    "corner": ("CORNER", "CornerLab", "Corners · totals, team totals and handicaps"),
    "card": ("CARD", "CardLab", "Cards · totals, team cards and referee-sensitive models"),
}


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


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


def _money(minor: int | None, currency: str) -> str:
    if minor is None:
        return "—"
    sign = "-" if minor < 0 else ""
    value = abs(minor) / 100
    return f"{sign}{value:,.2f} {currency}"


def _rate(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.2f}"


def _score(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.3f}"


def _provenance(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "—"
    parts: list[str] = []
    for key in (
        "referee_card_rate",
        "referee_foul_rate",
        "derby_rivalry_indicator",
        "table_pressure",
        "match_importance",
    ):
        item = payload.get(key)
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown")
        version = str(item.get("version") or "unknown")
        available = str(item.get("available_at") or "unavailable")
        parts.append(f"{key}: {source} · {version} · {available}")
    return " | ".join(parts) if parts else "—"


def _bookmaker_badge(name: Any) -> str:
    raw = str(name or "Unavailable")
    key = "".join(char for char in raw.casefold() if char.isalnum())
    if key == "bet365":
        mark = '<span class="brand-bet365"><b>bet</b><strong>365</strong></span>'
    elif key == "1xbet":
        mark = '<span class="brand-1xbet"><b>1X</b><strong>BET</strong></span>'
    else:
        mark = escape(raw)
    return (
        f'<span class="bookmaker-mark bookmaker-{escape(key or "generic")}" '
        f'title="{escape(raw, quote=True)}">{mark}</span>'
    )


def _clv_ppm(row: dict[str, Any]) -> int | None:
    closing = row.get("closing_odds")
    closing_at = row.get("closing_observed_at")
    entry_at = row.get("quote_observed_at")
    if closing is None or not isinstance(closing_at, datetime) or not isinstance(entry_at, datetime):
        return None
    if closing_at <= entry_at:
        return None
    return realized_clv_ppm(Decimal(str(row["odds"])), Decimal(str(closing)))


def _clv_text(ppm: int | None) -> str:
    return "—" if ppm is None else f"{ppm / 10_000:+.2f}%"


def _drawdown(rows: tuple[dict[str, Any], ...]) -> int:
    chronological = sorted(
        (row for row in rows if row.get("pnl_minor") is not None),
        key=lambda row: (row.get("settled_at") or row["decision_at"], row["shadow_bet_id"]),
    )
    equity = peak = 0
    max_drawdown = 0
    for row in chronological:
        equity += int(row["pnl_minor"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


class QuantLabDashboardService:
    def __init__(
        self,
        repository: PostgreSQLQuantLabRepository,
        *,
        api_daily_limit: int = 1000,
        currency: str = "RSD",
    ) -> None:
        if api_daily_limit <= 0:
            raise ValueError("api_daily_limit must be positive")
        self._repository = repository
        self._api_limit = api_daily_limit
        self._currency = currency

    def _filtered_rows(
        self,
        lab: str,
        params: dict[str, list[str]],
    ) -> tuple[dict[str, Any], ...]:
        rows = self._repository.list_bets(lab)
        bookmaker = params.get("bookmaker", [""])[0].strip().casefold()
        outcome = params.get("outcome", [""])[0].strip().upper()
        league = params.get("league", [""])[0].strip().casefold()
        market = params.get("market", [""])[0].strip().casefold()

        def keep(row: dict[str, Any]) -> bool:
            if bookmaker and bookmaker not in str(row.get("bookmaker_name") or "").casefold():
                return False
            if outcome and str(row.get("outcome") or "").upper() != outcome:
                return False
            if league and league not in str(row.get("competition_name") or "").casefold():
                return False
            return not (
                market and market not in str(row.get("market_key") or "").casefold()
            )

        return tuple(row for row in rows if keep(row))

    def render_html(self, raw_query: str = "") -> str:
        params = parse_qs(raw_query, keep_blank_values=True)
        lab_key = params.get("lab", ["goal"])[0].strip().casefold()
        if lab_key not in LABS:
            lab_key = "goal"
        lab, title, subtitle = LABS[lab_key]
        rows = self._filtered_rows(lab, params)
        settled = tuple(row for row in rows if row.get("outcome") in {"WIN", "LOSS", "VOID"})
        wins = sum(1 for row in settled if row.get("outcome") == "WIN")
        losses = sum(1 for row in settled if row.get("outcome") == "LOSS")
        pnl = sum(int(row["pnl_minor"]) for row in settled if row.get("pnl_minor") is not None)
        risked = sum(int(row["stake_minor"]) for row in settled)
        roi = None if risked == 0 else pnl / risked
        win_rate = None if wins + losses == 0 else wins / (wins + losses)
        clvs = [value for row in settled if (value := _clv_ppm(row)) is not None]
        avg_clv = None if not clvs else sum(clvs) / len(clvs)
        max_dd = _drawdown(rows)
        api_used = self._repository.api_usage_today()

        def query_for(target: str) -> str:
            current = {key: values[0] for key, values in params.items() if values and key != "lab"}
            current["lab"] = target
            return "?" + urlencode(current)

        tabs = "".join(
            f'<a class="{"active" if key == lab_key else ""}" href="{escape(query_for(key), quote=True)}">'
            f'{escape(meta[1])}</a>'
            for key, meta in LABS.items()
        )

        def field(name: str) -> str:
            return escape(params.get(name, [""])[0], quote=True)

        rows_html = ""
        for row in rows:
            pnl_minor = row.get("pnl_minor")
            pnl_class = "positive" if (pnl_minor or 0) > 0 else "negative" if (pnl_minor or 0) < 0 else "neutral"
            outcome = str(row.get("outcome") or "PENDING").upper()
            outcome_class = {
                "WIN": "result-win",
                "LOSS": "result-loss",
                "VOID": "result-void",
            }.get(outcome, "result-pending")
            match = f'{escape(str(row.get("home_team") or "?"))} – {escape(str(row.get("away_team") or "?"))}'
            league_text = escape(str(row.get("competition_name") or "—"))
            line = "—" if row.get("line") is None else escape(str(row["line"]))
            rows_html += (
                "<tr>"
                f'<td class="match"><b>{match}</b><small>{league_text} · {_time(row.get("kickoff_at"))}</small></td>'
                f'<td>{_bookmaker_badge(row.get("bookmaker_name"))}</td>'
                f'<td><b>{escape(str(row.get("market_key") or "—"))}</b>'
                f'<small>{escape(str(row.get("provider_bet_name") or "—"))}</small></td>'
                f'<td>{escape(str(row.get("selection") or "—"))}</td>'
                f"<td>{line}</td>"
                f'<td>{escape(str(row.get("model_name") or "—"))}<small>{escape(str(row.get("model_version") or "—"))}</small></td>'
                f"<td>{_pct(row.get('model_probability'))}</td>"
                f"<td>{_odd(row.get('odds'))}</td>"
                f"<td>{_pct(row.get('edge'))}</td>"
                f"<td>{_pct(row.get('expected_value'))}</td>"
                f"<td>{_odd(row.get('closing_odds'))}<small>{_clv_text(_clv_ppm(row))} CLV</small></td>"
                f'<td><span class="badge {outcome_class}">{escape(outcome)}</span></td>'
                f'<td class="{pnl_class}">{_money(None if pnl_minor is None else int(pnl_minor), self._currency)}</td>'
                f"<td>{_time(row.get('decision_at'))}</td>"
                "</tr>"
            )
        if not rows_html:
            rows_html = (
                '<tr><td class="empty" colspan="14">'
                f'No {escape(title)} shadow bets yet. The ledger is ready for QuantLab ingestion.'
                "</td></tr>"
            )

        card_context_html = ""
        if lab_key == "card":
            context_rows = self._repository.list_card_features()
            rendered_context = ""
            for item in context_rows:
                rivalry = item.get("derby_rivalry_indicator")
                rivalry_text = "UNKNOWN" if rivalry is None else "YES" if int(rivalry) == 1 else "NO"
                match = (
                    f'{escape(str(item.get("home_team") or "?"))} – '
                    f'{escape(str(item.get("away_team") or "?"))}'
                )
                rendered_context += (
                    "<tr>"
                    f'<td class="match"><b>{match}</b><small>{escape(str(item.get("competition_name") or "—"))} · {_time(item.get("kickoff_at"))}</small></td>'
                    f'<td>{escape(str(item.get("referee") or "UNKNOWN"))}</td>'
                    f'<td>{_rate(item.get("referee_card_rate"))}<small>n={int(item.get("referee_sample_size") or 0)}</small></td>'
                    f'<td>{_rate(item.get("referee_foul_rate"))}<small>n={int(item.get("referee_foul_sample_size") or 0)}</small></td>'
                    f'<td>{escape(rivalry_text)}</td>'
                    f'<td>{_score(item.get("home_table_pressure"))}</td>'
                    f'<td>{_score(item.get("away_table_pressure"))}</td>'
                    f'<td>{_score(item.get("match_importance"))}</td>'
                    f'<td>{_time(item.get("available_at"))}<small>{escape(str(item.get("feature_version") or "—"))}</small></td>'
                    f'<td class="provenance">{escape(_provenance(item.get("feature_payload")))}</td>'
                    "</tr>"
                )
            if not rendered_context:
                rendered_context = (
                    '<tr><td class="empty" colspan="10">'
                    'No CardLab v1 feature snapshots yet. Missing values are never fabricated.'
                    "</td></tr>"
                )
            card_context_html = (
                '<section class="table-shell context-table">'
                '<div class="table-title"><b>CardLab v1 context snapshots</b>'
                f'<span>{len(context_rows)} fixtures</span></div>'
                '<div class="table"><table><thead><tr>'
                '<th>Match</th><th>Referee</th><th>Cards / match</th><th>Fouls / match</th>'
                '<th>Derby</th><th>Home pressure</th><th>Away pressure</th><th>Importance</th>'
                '<th>Snapshot</th><th>Provenance</th>'
                f'</tr></thead><tbody>{rendered_context}</tbody></table></div></section>'
            )

        api_pct = min(100.0, api_used / self._api_limit * 100)
        cards = (
            ("Shadow bets", str(len(rows))),
            ("Settled", str(len(settled))),
            ("P&L", _money(pnl, self._currency)),
            ("ROI", "—" if roi is None else f"{roi * 100:+.2f}%"),
            ("Win rate", "—" if win_rate is None else f"{win_rate * 100:.1f}%"),
            ("Avg CLV", "—" if avg_clv is None else f"{avg_clv / 10_000:+.2f}%"),
            ("Max drawdown", _money(max_dd, self._currency)),
            ("QuantLab API", f"{api_used:,} / {self._api_limit:,}"),
        )
        cards_html = "".join(
            f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
            for label, value in cards
        )

        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantLab · {escape(title)}</title>
<style>
:root{{--bg:#101316;--panel:#181c20;--panel2:#20252a;--line:#30363c;--text:#edf0f2;--muted:#9099a2;--win:#69c98f;--loss:#e06f78;--warn:#d5aa61}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#171b1f 0,var(--bg) 220px);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1920px;margin:auto;padding:24px}}.topbar{{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:18px}}
.eyebrow{{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#aab2b9;font-weight:900}}h1{{margin:5px 0 4px;font-size:28px}}.subtitle{{margin:0;color:var(--muted);font-size:13px}}
.readonly{{padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:#171b1f;color:#aeb6bd;font-size:11px;font-weight:900}}
.tabs{{display:flex;gap:7px;width:max-content;padding:5px;margin-bottom:14px;border:1px solid var(--line);border-radius:12px;background:#15191c}}
.tabs a{{text-decoration:none;color:#9ba4ac;padding:10px 18px;border-radius:8px;font-weight:900;font-size:13px}}.tabs a.active{{background:#e4e7e9;color:#14171a}}
.lab-note{{margin:0 0 14px;padding:11px 13px;border-left:3px solid var(--warn);background:#171b1f;color:#aab2b9;font-size:12px}}
.cards{{display:grid;grid-template-columns:repeat(8,minmax(125px,1fr));gap:9px;margin-bottom:14px}}
.card{{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:12px;padding:13px 14px;min-height:82px}}
.card small{{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:900}}.card b{{display:block;margin-top:9px;font-size:20px}}
.api-bar{{height:5px;background:#252a2f;border-radius:999px;overflow:hidden;margin:-7px 0 16px}}.api-bar span{{display:block;height:100%;width:{api_pct:.2f}%;background:#c6a35d}}
.toolbar{{padding:10px 11px;margin-bottom:12px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}}form{{display:flex;gap:7px;flex-wrap:wrap}}
input,select,button{{height:36px;padding:0 10px;border:1px solid #3a4249;border-radius:8px;background:#121518;color:var(--text);font:inherit;font-size:12px}}input{{width:180px}}button{{background:#e1e4e6;color:#17191b;font-weight:900;cursor:pointer}}
.table-shell{{overflow:hidden;border:1px solid var(--line);border-radius:13px;background:var(--panel)}}.table-title{{display:flex;justify-content:space-between;padding:13px 14px;border-bottom:1px solid var(--line)}}.table{{overflow:auto;max-height:68vh}}
table{{border-collapse:separate;border-spacing:0;width:100%;font-size:12px}}th,td{{padding:10px 11px;border-bottom:1px solid #262c31;text-align:left;white-space:nowrap;vertical-align:middle}}
th{{position:sticky;top:0;background:#1c2125;color:#9099a2;text-transform:uppercase;letter-spacing:.06em;font-size:9px;z-index:2}}td.match{{min-width:250px}}small{{display:block;color:var(--muted);font-size:10px;margin-top:4px}}
.bookmaker-mark{{display:inline-flex;align-items:center;justify-content:center;min-width:82px;height:27px;padding:0 8px;border-radius:7px;font-weight:950}}.bookmaker-bet365{{background:#146947}}.brand-bet365 strong{{color:#f3d24b}}.bookmaker-1xbet{{background:#182f47}}.brand-1xbet b{{color:#61aef4}}.brand-1xbet strong{{color:white}}
.badge{{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:9px;font-weight:950}}.result-win{{color:#82dda6;background:rgba(105,201,143,.14)}}.result-loss{{color:#f08790;background:rgba(224,111,120,.14)}}.result-void{{color:#b6bdc3;background:rgba(154,161,168,.12)}}.result-pending{{color:#d7b36f;background:rgba(198,163,93,.12)}}
.positive{{color:var(--win)}}.negative{{color:var(--loss)}}.neutral{{color:var(--text)}}.empty{{text-align:center;padding:42px!important;color:var(--muted)}}
.context-table{{margin-bottom:12px}}td.provenance{{max-width:520px;white-space:normal;line-height:1.45;color:var(--muted)}}
footer{{margin-top:12px;color:#7f878e;font-size:11px;line-height:1.6}}
@media(max-width:1200px){{.cards{{grid-template-columns:repeat(4,1fr)}}}}@media(max-width:700px){{main{{padding:14px}}.topbar{{flex-direction:column}}.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<header class="topbar"><div><div class="eyebrow">QuantBet · QuantLab</div><h1>{escape(title)}</h1><p class="subtitle">{escape(subtitle)}</p></div><div class="readonly">● SHADOW ONLY · NO PRODUCTION WRITES</div></header>
<nav class="tabs">{tabs}</nav>
<p class="lab-note">Bet365 + 1xBet universe · flat shadow ledger · identical P&amp;L / ROI / CLV definitions across all three labs.</p>
<section class="cards">{cards_html}</section><div class="api-bar" title="QuantLab API budget used today"><span></span></div>
<section class="toolbar"><form method="get"><input type="hidden" name="lab" value="{escape(lab_key, quote=True)}">
<select name="bookmaker"><option value="">All bookmakers</option><option {"selected" if field("bookmaker").casefold()=="bet365" else ""}>Bet365</option><option {"selected" if field("bookmaker").casefold()=="1xbet" else ""}>1xBet</option></select>
<select name="outcome"><option value="">All outcomes</option>{''.join(f'<option {"selected" if field("outcome")==item else ""}>{item}</option>' for item in ("PENDING","WIN","LOSS","VOID"))}</select>
<input name="league" placeholder="League" value="{field("league")}"><input name="market" placeholder="Market" value="{field("market")}"><button type="submit">Apply</button></form></section>
{card_context_html}
<section class="table-shell"><div class="table-title"><b>{escape(title)} shadow ledger</b><span>{len(rows)} shown</span></div><div class="table"><table><thead><tr>
<th>Match</th><th>Bookmaker</th><th>Market</th><th>Selection</th><th>Line</th><th>Model</th><th>Model p</th><th>Odds</th><th>Edge</th><th>EV</th><th>Close / CLV</th><th>Result</th><th>P/L</th><th>Decision</th>
</tr></thead><tbody>{rows_html}</tbody></table></div></section>
<footer>QuantLab is analytically isolated from production registration and bankroll. GoalLab = goal models/DC+; CornerLab = corner models; CardLab = card/referee models. Times are Europe/Belgrade.</footer>
</main></body></html>"""


class QuantLabDashboardHTTPService:
    def __init__(self, dashboard: QuantLabDashboardService, *, host: str, port: int) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path == "/livez":
                    service._text(self, 200, "ok\n", "text/plain; charset=utf-8")
                    return
                if parsed.path not in {"/", "/quantlab"}:
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
                except Exception as exc:  # noqa: BLE001
                    service._text(self, 503, type(exc).__name__ + "\n", "text/plain; charset=utf-8")

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
        public = os.environ.get("QUANTBET_QUANTLAB_PUBLIC", "").strip().casefold()
        if public in {"1", "true", "yes", "on"}:
            return True
        password = os.environ.get("QUANTBET_QUANTLAB_PASSWORD", "")
        username = os.environ.get("QUANTBET_QUANTLAB_USER", "quantbet")
        if not password:
            QuantLabDashboardHTTPService._text(
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
        encoded = b"authentication_required\n"
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="QuantLab"')
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
