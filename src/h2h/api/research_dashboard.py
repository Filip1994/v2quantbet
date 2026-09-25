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
from urllib.parse import parse_qs, urlencode, urlsplit
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
        qualified_at = row.get("qualified_at") or row.get("first_blocked_at")
        if not isinstance(qualified_at, datetime):
            raise TypeError("qualified_at must be a datetime")

        rank = (
            qualified_at,
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
            key=lambda row: (
                row.get("qualified_at") or row.get("last_blocked_at"),
                str(row["evaluation_id"]),
            ),
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
        qualified_at = item.get("qualified_at") or item.get("first_blocked_at")
        if not isinstance(qualified_at, datetime):
            raise TypeError("qualified_at must be a datetime")
        quote_age = max(
            0,
            int((qualified_at - item["quote_observed_at"]).total_seconds()),
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
        disposition = params.get("disposition", [""])[0].strip().upper()
        p_bucket = params.get("p_bucket", [""])[0].strip()
        ev_bucket = params.get("ev_bucket", [""])[0].strip()
        odds_bucket = params.get("odds_bucket", [""])[0].strip()
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
            if disposition and row.get("disposition") != disposition:
                return False
            if p_bucket and row["probability_bucket"] != p_bucket:
                return False
            if ev_bucket and row["ev_bucket"] != ev_bucket:
                return False
            if odds_bucket and row["odds_bucket"] != odds_bucket:
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
        tab = params.get("tab", ["active"])[0].strip().casefold()
        if tab not in {"active", "history"}:
            tab = "active"

        metric_params = {
            key: value
            for key, value in params.items()
            if key not in {"tab", "result"}
        }
        filtered = self.signals(metric_params)

        def kickoff_timestamp(row: dict[str, Any]) -> float:
            kickoff = row.get("kickoff_at")
            return kickoff.timestamp() if isinstance(kickoff, datetime) else float("inf")

        active_rows = tuple(
            sorted(
                (row for row in filtered if row["outcome"] == "PENDING"),
                key=kickoff_timestamp,
            )
        )
        history_rows = tuple(
            sorted(
                (row for row in filtered if row["outcome"] != "PENDING"),
                key=kickoff_timestamp,
                reverse=True,
            )
        )
        result_filter = params.get("result", [""])[0].strip().upper()
        rows = (
            tuple(
                row
                for row in history_rows
                if not result_filter or row["outcome"] == result_filter
            )
            if tab == "history"
            else active_rows
        )

        settled = history_rows
        wins = sum(row["outcome"] == "WIN" for row in settled)
        clvs = [row["clv_ppm"] for row in settled if row["clv_ppm"] is not None]
        positive_clvs = sum(value > 0 for value in clvs)
        pnl = sum(row["pnl_minor"] or 0 for row in settled)
        win_rate = (wins / len(settled) * 100) if settled else None
        avg_clv = (sum(clvs) / len(clvs) / 10_000) if clvs else None
        positive_clv_rate = (positive_clvs / len(clvs) * 100) if clvs else None

        def field(name: str) -> str:
            return escape(params.get(name, [""])[0], quote=True)

        def tab_href(next_tab: str) -> str:
            query_params = {
                key: value[0]
                for key, value in params.items()
                if value and value[0] and key not in {"tab", "result"}
            }
            query_params["tab"] = next_tab
            return "/research?" + urlencode(query_params)

        def signed_class(value: float | None) -> str:
            if value is None or value == 0:
                return "neutral"
            return "positive" if value > 0 else "negative"

        def market_label(row: dict[str, Any]) -> str:
            market = "O/U 2.5" if row["market"] == "OU_25" else row["market"]
            return f'{market} {row["selection"]}'

        def result_badge(outcome: str) -> str:
            css = {
                "WIN": "win",
                "LOSS": "loss",
                "VOID": "void",
                "PENDING": "pending",
            }.get(outcome, "void")
            return f'<span class="badge result-{css}">{escape(outcome)}</span>'

        def disposition_badge(disposition: str) -> str:
            css = {
                "PLAYED": "played",
                "SKIPPED": "skipped",
                "BLOCKED_EXPOSURE": "blocked",
            }.get(disposition, "skipped")
            label = disposition.replace("_", " ")
            return f'<span class="badge route-{css}">{escape(label)}</span>'

        def freshness_badge(value: str) -> str:
            css = {
                "FRESH": "fresh",
                "USABLE_STALE": "stale",
                "HARD_STALE": "hard-stale",
            }.get(value, "void")
            label = value.replace("_", " ")
            return f'<span class="mini-badge freshness-{css}">{escape(label)}</span>'

        body_rows: list[str] = []
        if tab == "active":
            for row in rows:
                exposure = (
                    "—"
                    if row["last_open_exposure_minor"] is None
                    or row["exposure_cap_minor"] is None
                    else (
                        f'{row["last_open_exposure_minor"] / 100:.0f}/'
                        f'{row["exposure_cap_minor"] / 100:.0f} RSD'
                    )
                )
                match = f'{escape(row["home_team"])} – {escape(row["away_team"])}'
                competition = escape(row.get("competition_name") or "—")
                body_rows.append(
                    '<tr class="row-pending">'
                    f'<td class="match"><b>{match}</b>'
                    f'<small>{competition} · fixture {escape(str(row["provider_fixture_id"]))}</small></td>'
                    f'<td><b>{_time(row["kickoff_at"])}</b></td>'
                    f'<td><span class="pick-pill">{escape(market_label(row))}</span></td>'
                    f'<td><b>{_pct(row["model_probability"])}</b>'
                    f'<small>fair {_pct(row["market_fair_probability"])} · {escape(row["probability_bucket"])}</small></td>'
                    f'<td><b>{_odd(row["odds"])}</b><small>{escape(row["odds_bucket"])}</small></td>'
                    f'<td>{disposition_badge(row["disposition"])}</td>'
                    f'<td class="{signed_class(row["edge"])}"><b>{_pct(row["edge"])}</b></td>'
                    f'<td class="{signed_class(row["expected_value"])}"><b>{_pct(row["expected_value"])}</b>'
                    f'<small>{escape(row["ev_bucket"])}</small></td>'
                    f'<td><b>{escape(row["bookmaker"])}</b><small>{escape(row["source"])}</small></td>'
                    f'<td>{_time(row["qualified_at"])}'
                    f'<small>{row["quote_age_seconds"]}s · {freshness_badge(row["freshness"])}</small></td>'
                    f'<td><b>{exposure}</b><small>'
                    f'{"blocked ×" + str(row["blocked_count"]) if row["blocked_count"] is not None else "production candidate"}'
                    f'</small></td>'
                    f'<td>{result_badge(row["outcome"])}</td>'
                    "</tr>"
                )
            headers = (
                "<th>Match</th><th>Kickoff</th><th>Pick</th><th>Model</th>"
                "<th>Odds</th><th>Route</th><th>Edge</th><th>EV</th><th>Bookmaker</th>"
                "<th>Qualified</th><th>Exposure</th><th>Status</th>"
            )
            empty_text = "No active research picks match these filters."
            colspan = 12
        else:
            for row in rows:
                clv_value = (
                    None if row["clv_ppm"] is None else row["clv_ppm"] / 10_000
                )
                clv = "—" if clv_value is None else f"{clv_value:+.2f}%"
                pnl_value = None if row["pnl_minor"] is None else row["pnl_minor"] / 100
                pnl_rsd = "—" if pnl_value is None else f"{pnl_value:+.0f} RSD"
                match = f'{escape(row["home_team"])} – {escape(row["away_team"])}'
                competition = escape(row.get("competition_name") or "—")
                home = row.get("regulation_home_goals")
                away = row.get("regulation_away_goals")
                score = (
                    f"{home}–{away}"
                    if home is not None and away is not None
                    else "—"
                )
                row_class = f'row-{row["outcome"].casefold()}'
                body_rows.append(
                    f'<tr class="{row_class}">'
                    f'<td class="match"><b>{match}</b>'
                    f'<small>{competition} · fixture {escape(str(row["provider_fixture_id"]))}</small></td>'
                    f'<td><span class="pick-pill">{escape(market_label(row))}</span></td>'
                    f'<td>{_time(row["kickoff_at"])}</td>'
                    f'<td><b>{_odd(row["odds"])}</b><small>{escape(row["odds_bucket"])} · {escape(row["bookmaker"])}</small></td>'
                    f'<td><b>{_odd(row["closing_odds"])}</b><small>{_time(row["closing_observed_at"])}</small></td>'
                    f'<td class="{signed_class(clv_value)}"><b>{clv}</b></td>'
                    f'<td><b>{_pct(row["model_probability"])}</b>'
                    f'<small>{escape(row["probability_bucket"])} · fair {_pct(row["market_fair_probability"])}</small></td>'
                    f'<td class="{signed_class(row["expected_value"])}"><b>{_pct(row["expected_value"])}</b>'
                    f'<small>{escape(row["ev_bucket"])}</small></td>'
                    f'<td>{disposition_badge(row["disposition"])}</td>'
                    f'<td>{result_badge(row["outcome"])}'
                    f'<small>{score} · {escape(row.get("result_provider_status") or row.get("result_phase") or "settled")}</small></td>'
                    f'<td class="{signed_class(pnl_value)}"><b>{pnl_rsd}</b></td>'
                    f'<td><b>{escape(row["bookmaker"])}</b><small>{escape(row["source"])}</small></td>'
                    f'<td>{_time(row["qualified_at"])}</td>'
                    "</tr>"
                )
            headers = (
                "<th>Match</th><th>Pick</th><th>Kickoff</th><th>Entry</th>"
                "<th>Research close</th><th>CLV</th><th>Model</th><th>EV</th>"
                "<th>Route</th><th>Result</th><th>P/L</th><th>Bookmaker</th><th>Qualified</th>"
            )
            empty_text = "No historical research picks match these filters."
            colspan = 13

        rows_html = (
            "".join(body_rows)
            or f'<tr><td class="empty" colspan="{colspan}">{empty_text}</td></tr>'
        )
        win_rate_text = "—" if win_rate is None else f"{win_rate:.1f}%"
        avg_clv_text = "—" if avg_clv is None else f"{avg_clv:+.2f}%"
        positive_clv_text = (
            "—" if positive_clv_rate is None else f"{positive_clv_rate:.1f}%"
        )
        pnl_text = f"{pnl / 100:+.0f} RSD"
        pnl_class = signed_class(pnl)
        avg_clv_class = signed_class(avg_clv)

        result_filter_html = ""
        if tab == "history":
            options = "".join(
                f'<option {"selected" if field("result") == value else ""}>{value}</option>'
                for value in ("WIN", "LOSS", "VOID")
            )
            result_filter_html = (
                '<select name="result" aria-label="Result filter">'
                '<option value="">All results</option>'
                + options
                + "</select>"
            )

        active_class = "active" if tab == "active" else ""
        history_class = "active" if tab == "history" else ""
        active_href = escape(tab_href("active"), quote=True)
        history_href = escape(tab_href("history"), quote=True)
        clear_href = f"/research?tab={tab}"

        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantBet Research</title><style>
:root{{--bg:#111315;--panel:#181b1f;--panel-2:#1c2024;--panel-3:#22272c;--line:#30363d;--line-soft:#252a2f;--text:#eceff1;--muted:#9299a1;--accent:#c2c8ce;--accent-soft:rgba(194,200,206,.10);--blue:#86a6c2;--win:#69c98f;--loss:#e06f78;--warn:#c6a35d;--void:#9aa1a8;color-scheme:dark;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#14171a 0%,var(--bg) 180px);color:var(--text)}}
main{{max-width:1920px;margin:auto;padding:24px}}.topbar{{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:22px}}
.brand{{display:flex;align-items:center;gap:12px}}.brand-mark{{width:42px;height:42px;border-radius:12px;background:linear-gradient(145deg,#d4d8dc,#8f969d);display:grid;place-items:center;font-weight:900;color:#15181b;box-shadow:0 10px 28px rgba(0,0,0,.22);border:1px solid #d8dde1}}
h1{{font-size:24px;line-height:1.1;margin:0}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.14em;color:#aab1b8;font-weight:800;margin-bottom:4px}}
.subtitle{{margin:0;color:var(--muted);font-size:13px}}.readonly{{border:1px solid var(--line);background:#1a1e22;padding:8px 11px;border-radius:999px;color:#aeb5bc;font-size:12px;white-space:nowrap}}
.tabs{{display:flex;gap:8px;margin:0 0 16px;padding:5px;background:#171a1d;border:1px solid var(--line);border-radius:12px;width:max-content}}
.tabs a{{text-decoration:none;color:#9ca3aa;padding:9px 16px;border-radius:8px;font-weight:800;font-size:13px;transition:.15s ease}}
.tabs a:hover{{color:var(--text);background:#24292e}}.tabs a.active{{background:#d4d8dc;color:#17191b;box-shadow:0 5px 16px rgba(0,0,0,.24)}}
.cards{{display:grid;grid-template-columns:repeat(6,minmax(145px,1fr));gap:10px;margin-bottom:14px}}
.card{{position:relative;overflow:hidden;background:linear-gradient(180deg,var(--panel-2),var(--panel));border:1px solid var(--line);border-radius:12px;padding:14px 15px;min-height:84px}}
.card:after{{content:"";position:absolute;width:72px;height:72px;border-radius:50%;right:-26px;top:-30px;background:rgba(255,255,255,.028)}}
.card small{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em;font-weight:800}}.card b{{display:block;font-size:22px;margin-top:8px;letter-spacing:-.02em}}
.card .positive{{color:var(--win)}}.card .negative{{color:var(--loss)}}.card .neutral{{color:var(--text)}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:12px}}
form{{display:flex;gap:7px;flex-wrap:wrap;align-items:center;flex:1}}input,select,button{{height:36px;background:#14171a;color:var(--text);border:1px solid #3a4046;border-radius:8px;padding:0 10px;font:inherit;font-size:12px;outline:none}}
input{{width:132px}}input[name="league"]{{width:170px}}input:focus,select:focus{{border-color:#8f969d;box-shadow:0 0 0 2px rgba(194,200,206,.08)}}
button{{background:#d4d8dc;color:#17191b;border-color:#d4d8dc;font-weight:900;cursor:pointer;padding:0 14px}}button:hover{{background:#e2e5e8;border-color:#e2e5e8}}
.clear{{color:#a4b4ab;text-decoration:none;font-size:12px;padding:8px 6px}}.clear:hover{{color:white}}
.table-shell{{background:var(--panel);border:1px solid var(--line);border-radius:13px;overflow:hidden;box-shadow:0 18px 60px rgba(0,0,0,.17)}}
.table-title{{display:flex;align-items:center;justify-content:space-between;padding:13px 15px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#1e2226,#191c20)}}
.table-title b{{font-size:14px}}.table-title span{{font-size:12px;color:var(--muted)}}.table{{overflow:auto;max-height:70vh}}
table{{border-collapse:separate;border-spacing:0;width:100%;font-size:12px}}th,td{{padding:11px 12px;border-bottom:1px solid var(--line-soft);text-align:left;white-space:nowrap;vertical-align:middle}}
th{{position:sticky;top:0;z-index:3;background:#1b1f23;color:#959da5;text-transform:uppercase;letter-spacing:.06em;font-size:10px;font-weight:900}}
tbody tr{{transition:background .12s ease}}tbody tr:hover{{background:#20252a}}tbody tr:last-child td{{border-bottom:0}}
td.match{{min-width:250px}}td b{{font-weight:800}}small{{display:block;color:var(--muted);margin-top:4px;font-size:10px}}
.pick-pill{{display:inline-flex;align-items:center;padding:6px 9px;border-radius:7px;background:#24292e;border:1px solid #3a4046;color:#e6e9ec;font-weight:900;font-size:11px}}
.badge{{display:inline-flex;align-items:center;justify-content:center;min-width:68px;padding:6px 9px;border-radius:999px;font-weight:950;font-size:10px;letter-spacing:.06em}}
.result-win{{background:rgba(105,201,143,.11);border:1px solid rgba(105,201,143,.32);color:var(--win)}}.result-loss{{background:rgba(224,111,120,.11);border:1px solid rgba(224,111,120,.32);color:var(--loss)}}.result-void{{background:rgba(154,169,161,.12);border:1px solid rgba(154,169,161,.28);color:#b4c1ba}}.result-pending{{background:rgba(242,189,88,.12);border:1px solid rgba(242,189,88,.32);color:var(--warn)}}
.mini-badge{{display:inline-flex;padding:2px 6px;border-radius:999px;font-size:9px;font-weight:850;vertical-align:1px}}.freshness-fresh{{background:rgba(105,201,143,.10);color:var(--win)}}.freshness-stale{{background:rgba(198,163,93,.11);color:var(--warn)}}.freshness-hard-stale{{background:rgba(224,111,120,.10);color:var(--loss)}}
.positive{{color:var(--win)}}.negative{{color:var(--loss)}}.neutral{{color:var(--text)}}.row-win{{box-shadow:inset 3px 0 var(--win)}}.row-loss{{box-shadow:inset 3px 0 var(--loss)}}.row-void{{box-shadow:inset 3px 0 var(--void)}}.row-pending{{box-shadow:inset 3px 0 var(--warn)}}
.empty{{text-align:center!important;color:var(--muted);padding:40px!important}}footer{{display:flex;justify-content:space-between;gap:15px;color:#7f878e;margin-top:12px;font-size:11px}}
@media(max-width:1200px){{.cards{{grid-template-columns:repeat(3,1fr)}}.toolbar{{align-items:flex-start}}}}
@media(max-width:720px){{main{{padding:14px}}.topbar{{align-items:flex-start;flex-direction:column}}.cards{{grid-template-columns:repeat(2,1fr)}}.toolbar{{display:block}}form{{margin-bottom:7px}}input,input[name="league"],select{{width:calc(50% - 4px)}}footer{{display:block;line-height:1.6}}}}
</style></head><body><main>
<header class="topbar">
<div class="brand"><div class="brand-mark">QB</div><div><div class="eyebrow">Shadow intelligence</div><h1>QuantBet Research</h1><p class="subtitle">Exposure-blocked value signals · one canonical pick per fixture</p></div></div>
<div class="readonly">● READ-ONLY RESEARCH</div>
</header>
<nav class="tabs" aria-label="Research sections">
<a class="{active_class}" href="{active_href}">Active <span>({len(active_rows)})</span></a>
<a class="{history_class}" href="{history_href}">History <span>({len(history_rows)})</span></a>
</nav>
<section class="cards">
<div class="card"><small>Active picks</small><b>{len(active_rows)}</b></div>
<div class="card"><small>History</small><b>{len(history_rows)}</b></div>
<div class="card"><small>Win rate</small><b>{win_rate_text}</b></div>
<div class="card"><small>Flat P/L</small><b class="{pnl_class}">{pnl_text}</b></div>
<div class="card"><small>Avg research CLV</small><b class="{avg_clv_class}">{avg_clv_text}</b></div>
<div class="card"><small>Positive CLV</small><b>{positive_clv_text}</b></div>
</section>
<div class="toolbar">
<form method="get">
<input type="hidden" name="tab" value="{tab}">
<select name="market" aria-label="Market filter"><option value="">All markets</option><option {"selected" if field("market")=="BTTS" else ""}>BTTS</option><option {"selected" if field("market")=="OU_25" else ""}>OU_25</option></select>
<input name="league" placeholder="League" value="{field("league")}">
<input name="p_min" placeholder="Model p min %" value="{field("p_min")}">
<input name="p_max" placeholder="Model p max %" value="{field("p_max")}">
<input name="ev_min" placeholder="EV min %" value="{field("ev_min")}">
<input name="ev_max" placeholder="EV max %" value="{field("ev_max")}">
<input name="odds_min" placeholder="Odds min" value="{field("odds_min")}">
<input name="odds_max" placeholder="Odds max" value="{field("odds_max")}">
{result_filter_html}
<button type="submit">Apply filters</button><a class="clear" href="{clear_href}">Clear</a>
</form>
</div>
<section class="table-shell">
<div class="table-title"><b>{"Active research board" if tab == "active" else "Settled research history"}</b><span>{len(rows)} shown</span></div>
<div class="table"><table><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></div>
</section>
<footer><span>Research close = last stored same-series/source pre-kickoff quote. CLV is shown only when the closing quote is later than entry.</span><span>Times: Europe/Belgrade · Counterfactual flat stake only</span></footer>
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
