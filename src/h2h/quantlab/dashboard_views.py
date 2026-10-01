"""Simplified operational and analytics views for QuantLab.

This module is presentation-only. It reads the existing QuantLab ledgers and does not
write to production, alter model authority, or change collector/modeler/settlement logic.
Analytics bucket links resolve cohort rows back to their exact settled constituent picks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html import escape
from itertools import pairwise
import re
from typing import Any
from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from h2h.domain.settlement import realized_clv_ppm
from h2h.quantlab.goal_analytics import (
    build_goal_analytics_snapshot,
    calibration_bins,
    goal_pick_metrics,
)
from h2h.quantlab.goal_lab.explanations import render_goal_pick_note_html
from h2h.quantlab.note_dialog import NOTE_DIALOG_CSS, NOTE_DIALOG_HTML

BELGRADE = ZoneInfo("Europe/Belgrade")

LABS = {
    "goal": ("GOAL", "GoalLab", "Goals · DC+ and goal-market experiments"),
    "corner": ("CORNER", "CornerLab", "Corners · totals, team totals and handicaps"),
    "card": ("CARD", "CardLab", "Cards · totals, team cards and referee-sensitive models"),
}
ANALYTICS_LABS = {"goal", "corner", "card"}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Any, *, signed: bool = False) -> str:
    number = _number(value)
    if number is None:
        return "—"
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number * 100:.1f}%"


def _pct_points(value: Any, *, signed: bool = False) -> str:
    number = _number(value)
    if number is None:
        return "—"
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.2f}%"


def _odd(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.2f}"


def _time(value: Any) -> str:
    if not isinstance(value, datetime):
        return "—"
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(BELGRADE).strftime("%Y-%m-%d %H:%M")


def _money(minor: int | None, currency: str) -> str:
    if minor is None:
        return "—"
    sign = "-" if minor < 0 else ""
    value = abs(minor) / 100
    return f"{sign}{value:,.2f} {currency}"


def _result(row: dict[str, Any]) -> str:
    return str(row.get("outcome") or "PENDING").upper()


def _event_time(row: dict[str, Any]) -> datetime:
    value = row.get("settled_at") or row.get("kickoff_at") or row.get("decision_at")
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _pick_id(row: dict[str, Any]) -> str:
    return str(row.get("goal_pick_id") or row.get("shadow_bet_id") or row.get("fixture_id") or "")


def _sorted(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        sorted(
            rows,
            key=lambda row: (_event_time(row), _pick_id(row)),
            reverse=True,
        )
    )


def _bookmaker(name: Any) -> str:
    raw = str(name or "—")
    key = "".join(char for char in raw.casefold() if char.isalnum())
    if key == "bet365":
        return '<span class="bookmaker bookmaker-bet365">bet<strong>365</strong></span>'
    if key == "1xbet":
        return '<span class="bookmaker bookmaker-1xbet"><strong>1X</strong>BET</span>'
    return f'<span class="bookmaker">{escape(raw)}</span>'


def _result_badge(result: str) -> str:
    css = {
        "WIN": "result-win",
        "LOSS": "result-loss",
        "VOID": "result-void",
        "PENDING": "result-pending",
    }.get(result, "result-pending")
    return f'<span class="badge {css}">{escape(result)}</span>'


def _pick_text(row: dict[str, Any]) -> str:
    market = str(row.get("market_key") or row.get("provider_bet_name") or "—")
    selection = str(row.get("selection") or "—")
    line = row.get("line")
    line_text = "" if line is None else f" {line}"
    return f"{market} · {selection}{line_text}"


def _match_html(row: dict[str, Any], *, lab_key: str) -> str:
    label = (
        f'{escape(str(row.get("home_team") or "?"))} – '
        f'{escape(str(row.get("away_team") or "?"))}'
    )
    if lab_key == "goal" and row.get("goal_pick_id"):
        href = "/quantlab/goal/pick?" + urlencode(
            {"goal_pick_id": str(row["goal_pick_id"])}
        )
        label = f'<a href="{escape(href, quote=True)}">{label}</a>'
    competition = escape(str(row.get("competition_name") or "—"))
    return (
        f'<td class="match"><b>{label}</b>'
        f'<small>{competition} · {_time(row.get("kickoff_at"))}</small></td>'
    )


def _display_rows(repository: Any, lab: str) -> tuple[dict[str, Any], ...]:
    if lab == "GOAL":
        return tuple(repository.list_goal_picks())
    return tuple(repository.list_bets(lab))


def _all_rows(repository: Any, lab: str) -> tuple[dict[str, Any], ...]:
    if lab == "GOAL":
        loader = getattr(repository, "list_all_goal_picks", None)
        if callable(loader):
            return tuple(loader())
        return tuple(repository.list_goal_picks())
    loader = getattr(repository, "list_all_bets", None)
    if callable(loader):
        return tuple(loader(lab))
    return tuple(repository.list_bets(lab))


def _goal_notes(
    repository: Any,
    rows: tuple[dict[str, Any], ...],
) -> dict[str, str]:
    contracts: dict[str, dict[str, Any] | None] = {}
    rendered: dict[str, str] = {}
    loader = getattr(repository, "goal_model_contract", None)
    for row in rows:
        goal_pick_id = str(row.get("goal_pick_id") or "")
        if not goal_pick_id:
            continue
        model_version = str(row.get("model_version") or "")
        if model_version not in contracts:
            contract = None
            if callable(loader):
                try:
                    contract = loader(model_version) if model_version else loader()
                except Exception:  # noqa: BLE001 - notes must degrade without blocking dashboard
                    contract = None
            contracts[model_version] = contract
        href = "/quantlab/goal/pick?" + urlencode({"goal_pick_id": goal_pick_id})
        rendered[_pick_id(row)] = render_goal_pick_note_html(
            row,
            contracts[model_version],
            detail_href=href,
        )
    return rendered


def _card_notes(rows: tuple[dict[str, Any], ...]) -> dict[str, str]:
    rendered: dict[str, str] = {}

    def rate(value: Any) -> str:
        number = _number(value)
        return "—" if number is None else f"{number:.2f}"

    for row in rows:
        pick_id = _pick_id(row)
        if not pick_id:
            continue

        details = row.get("decision_details")
        details = details if isinstance(details, dict) else {}
        context = details.get("card_context")
        context = context if isinstance(context, dict) else {}
        thresholds = details.get("thresholds")
        thresholds = thresholds if isinstance(thresholds, dict) else {}
        probability_model = details.get("probability_model")
        probability_model = probability_model if isinstance(probability_model, dict) else {}

        expected = _number(details.get("expected_total_cards"))
        if expected is None:
            expected = _number(context.get("referee_card_rate"))
        referee = str(context.get("referee") or "—")
        referee_cards = _number(context.get("referee_card_rate"))
        referee_n = int(_number(context.get("referee_sample_size")) or 0)
        referee_fouls = _number(context.get("referee_foul_rate"))
        referee_foul_n = int(_number(context.get("referee_foul_sample_size")) or 0)
        rivalry = context.get("derby_rivalry_indicator")
        rivalry_text = "DA" if rivalry == 1 else "NE" if rivalry == 0 else "—"
        home_pressure = _number(context.get("home_table_pressure"))
        away_pressure = _number(context.get("away_table_pressure"))
        importance = _number(context.get("match_importance"))

        decision_reason = str(row.get("decision_reason") or "VALUE_THRESHOLD_PASSED")
        model_name = str(probability_model.get("name") or row.get("model_name") or "CardLab model")
        distribution = str(probability_model.get("distribution") or "Poisson")
        lambda_source = str(probability_model.get("lambda_source") or "referee_card_rate")

        summary = (
            f"{_pick_text(row)} @ {_odd(row.get('odds'))}: model {_pct(row.get('model_probability'))} "
            f"naspram market {_pct(row.get('market_probability'))}; "
            f"edge {_pct(row.get('edge'), signed=True)}, EV {_pct(row.get('expected_value'), signed=True)}."
        )
        model_text = (
            f"{model_name} koristi {distribution} raspodelu; očekivani total je {rate(expected)}. "
            f"λ izvor: {lambda_source}."
        )
        referee_text = (
            f"Sudija {referee}: {rate(referee_cards)} kartona/meč (n={referee_n}), "
            f"{rate(referee_fouls)} faulova/meč (n={referee_foul_n})."
        )
        context_text = (
            f"Kontekst: derbi {rivalry_text}; pritisak domaćin {rate(home_pressure)}, "
            f"gost {rate(away_pressure)}; važnost {rate(importance)}."
        )

        threshold_bits: list[str] = []
        if thresholds.get("min_edge") is not None:
            threshold_bits.append(f"edge ≥ {_pct(thresholds.get('min_edge'))}")
        if thresholds.get("min_expected_value") is not None:
            threshold_bits.append(f"EV ≥ {_pct(thresholds.get('min_expected_value'))}")
        if thresholds.get("min_odds") is not None and thresholds.get("max_odds") is not None:
            threshold_bits.append(
                f"odds {_odd(thresholds.get('min_odds'))}–{_odd(thresholds.get('max_odds'))}"
            )
        if thresholds.get("min_referee_sample_size") is not None:
            threshold_bits.append(
                f"referee n ≥ {int(_number(thresholds.get('min_referee_sample_size')) or 0)}"
            )
        gate_text = (
            "Gate: " + ", ".join(threshold_bits) + f"; odluka {decision_reason}."
            if threshold_bits
            else f"Odluka: {decision_reason}."
        )

        rendered[pick_id] = (
            '<details class="pick-note"><summary title="Zašto je CardLab izabrao ovaj pik">📝</summary>'
            '<div class="note-popover"><b>Zašto ovaj CardLab pik</b>'
            f'<p>{escape(summary)}</p>'
            f'<p>{escape(model_text)}</p>'
            f'<p>{escape(referee_text)}</p>'
            f'<p>{escape(context_text)}</p>'
            f'<p>{escape(gate_text)}</p>'
            '<p><b>Važno:</b> u aktuelnom CardLab modelu referee_card_rate je probability input; '
            'faulovi, derbi, table pressure i match importance su audit/research kontekst, '
            'ne ručno dodati koeficijenti u verovatnoću.</p>'
            '</div></details>'
        )
    return rendered


def _nav(view: str, lab_key: str) -> tuple[str, str]:
    analytics_lab = lab_key if lab_key in ANALYTICS_LABS else "goal"
    primary = (
        '<nav class="primary-tabs">'
        f'<a class="{"active" if view == "dashboard" else ""}" '
        f'href="/quantlab?{urlencode({"view": "dashboard", "lab": lab_key})}">Dashboard</a>'
        f'<a class="{"active" if view == "analytics" else ""}" '
        f'href="/quantlab?{urlencode({"view": "analytics", "lab": analytics_lab})}">Analytics</a>'
        "</nav>"
    )
    allowed = ANALYTICS_LABS if view == "analytics" else set(LABS)
    secondary = '<nav class="lab-tabs">' + "".join(
        f'<a class="{"active" if key == lab_key else ""}" '
        f'href="/quantlab?{urlencode({"view": view, "lab": key})}">{escape(LABS[key][1])}</a>'
        for key in LABS
        if key in allowed
    ) + "</nav>"
    return primary, secondary


def _shell(
    *,
    title: str,
    subtitle: str,
    view: str,
    lab_key: str,
    body: str,
) -> str:
    primary, secondary = _nav(view, lab_key)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantLab · {escape(title)} · {escape(view.title())}</title>
<style>
:root{{--bg:#0f1215;--panel:#181c20;--panel2:#20252a;--line:#30363c;--text:#edf0f2;--muted:#9099a2;--win:#69c98f;--loss:#e06f78;--warn:#d5aa61}}
*{{box-sizing:border-box}}
body{{margin:0;background:linear-gradient(180deg,#171b1f 0,var(--bg) 220px);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1760px;margin:auto;padding:24px}}
a{{color:#a9cdf8;text-decoration:none}}
.topbar{{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:16px}}
.eyebrow{{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#aab2b9;font-weight:900}}
h1{{margin:5px 0 4px;font-size:28px}}.subtitle{{margin:0;color:var(--muted);font-size:13px}}
.readonly{{padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:#171b1f;color:#aeb6bd;font-size:11px;font-weight:900}}
.primary-tabs,.lab-tabs{{display:flex;gap:7px;width:max-content;padding:5px;border:1px solid var(--line);border-radius:12px;background:#15191c}}
.primary-tabs{{margin-bottom:9px}}.lab-tabs{{margin-bottom:16px}}
.primary-tabs a,.lab-tabs a{{padding:9px 16px;border-radius:8px;color:#9ba4ac;font-size:12px;font-weight:900}}
.primary-tabs a.active,.lab-tabs a.active{{background:#e4e7e9;color:#14171a}}
.cards{{display:grid;grid-template-columns:repeat(8,minmax(120px,1fr));gap:9px;margin-bottom:14px}}
.card{{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:12px;padding:13px 14px;min-height:78px}}
.card small{{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:900}}
.card b{{display:block;margin-top:8px;font-size:19px}}
.panel{{overflow:hidden;border:1px solid var(--line);border-radius:13px;background:var(--panel);margin-bottom:12px}}
.panel-title{{display:flex;justify-content:space-between;gap:16px;padding:13px 14px;border-bottom:1px solid var(--line)}}
.panel-title span{{color:var(--muted);font-size:11px}}
.table{{overflow:auto;max-height:62vh}}
table{{border-collapse:separate;border-spacing:0;width:100%;font-size:12px}}
th,td{{padding:10px 11px;border-bottom:1px solid #262c31;text-align:left;white-space:nowrap;vertical-align:middle}}
th{{position:sticky;top:0;background:#1c2125;color:#9099a2;text-transform:uppercase;letter-spacing:.06em;font-size:9px;z-index:2}}
.sort-header{{display:inline-flex;align-items:center;gap:5px;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit;white-space:nowrap}}
.sort-header:hover,.sort-header.active{{color:#d8e5f2}}.sort-arrow{{font-size:10px;line-height:1}}
.group-link{{color:#dfe8f2;font-weight:900;text-decoration:underline;text-decoration-color:#4a6075;text-underline-offset:2px}}
.group-link:hover{{color:#a9cdf8;text-decoration-color:#a9cdf8}}
td.match{{min-width:250px}}small{{display:block;color:var(--muted);font-size:10px;margin-top:4px}}
.badge{{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:9px;font-weight:950}}
.result-win{{color:#82dda6;background:rgba(105,201,143,.14)}}.result-loss{{color:#f08790;background:rgba(224,111,120,.14)}}
.result-void{{color:#b6bdc3;background:rgba(154,161,168,.12)}}.result-pending{{color:#d7b36f;background:rgba(198,163,93,.12)}}
.positive{{color:var(--win)}}.negative{{color:var(--loss)}}.neutral{{color:var(--text)}}
.bookmaker{{display:inline-flex;align-items:center;justify-content:center;min-width:78px;height:27px;padding:0 8px;border-radius:7px;font-weight:900;background:#232a30}}
.bookmaker-bet365{{background:#146947}}.bookmaker-bet365 strong{{color:#f3d24b}}.bookmaker-1xbet{{background:#182f47}}.bookmaker-1xbet strong{{color:#61aef4}}
.notes-cell{{min-width:70px;white-space:normal}}
.pick-note summary{{list-style:none;cursor:pointer;font-size:16px;width:30px;height:30px;display:flex;align-items:center;justify-content:center;border:1px solid var(--line);border-radius:8px;background:#14181b}}
.pick-note summary::-webkit-details-marker{{display:none}}
.pick-note[open] summary{{background:#242b31}}
.note-popover{{width:min(640px,65vw);min-width:420px;margin-top:8px;padding:13px;border:1px solid #3b434a;border-radius:10px;background:#111518;white-space:normal;line-height:1.5;box-shadow:0 12px 30px rgba(0,0,0,.28)}}
.note-popover> b{{font-size:13px}}
.note-popover p{{margin:8px 0;color:#c1c8ce;font-size:11px;white-space:normal}}
.note-popover h4{{margin:12px 0 5px;font-size:11px}}
.note-popover ul{{margin:5px 0 8px;padding-left:18px;color:#b8c0c7;font-size:11px;line-height:1.55;white-space:normal}}
.note-detail-link{{display:inline-block;margin-top:8px;color:#9bc7ff;font-weight:900;font-size:11px}}
{NOTE_DIALOG_CSS}
.empty{{text-align:center;padding:34px!important;color:var(--muted)}}
.analytics-note{{margin:0 0 14px;padding:11px 13px;border-left:3px solid var(--warn);background:#171b1f;color:#aab2b9;font-size:12px}}
.analytics-section{{margin:22px 2px 10px;padding-top:5px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#c8d0d7}}
.analytics-section small{{display:inline;margin-left:9px;text-transform:none;letter-spacing:0;font-weight:400}}
.watchlist{{margin:8px 0 18px;padding:12px;border:2px solid #a9782c;border-radius:16px;background:linear-gradient(180deg,rgba(169,120,44,.12),rgba(169,120,44,.035));box-shadow:0 0 0 1px rgba(226,178,93,.08) inset}}
.watchlist-head{{display:flex;justify-content:space-between;align-items:baseline;gap:14px;padding:2px 2px 11px}}
.watchlist-head b{{color:#e5b45d;font-size:13px;letter-spacing:.12em;text-transform:uppercase}}
.watchlist-head span{{color:#aeb6bd;font-size:11px}}
.watchlist .panel{{border-color:#5b4726;background:#171b1e}}
.watchlist .panel-title{{background:rgba(169,120,44,.06)}}
.watchlist .panel-title b{{color:#f0d29a}}
.analytics-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:12px}}
.analytics-grid .panel{{margin:0}}
.metric-list{{padding:8px 14px 12px}}.metric-line{{display:flex;justify-content:space-between;gap:18px;padding:8px 0;border-bottom:1px solid #262c31}}
.metric-line:last-child{{border-bottom:0}}.metric-line span{{color:var(--muted)}}
.audit-pass{{color:var(--win)}}.audit-fail{{color:var(--loss)}}
footer{{margin-top:14px;color:#7f878e;font-size:11px;line-height:1.6}}
@media(max-width:1100px){{.cards{{grid-template-columns:repeat(4,1fr)}}.analytics-grid{{grid-template-columns:1fr}}}}
@media(max-width:700px){{main{{padding:14px}}.topbar{{flex-direction:column}}.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body><main>
<header class="topbar">
<div><div class="eyebrow">QuantBet · QuantLab</div><h1>{escape(title)}</h1><p class="subtitle">{escape(subtitle)}</p></div>
<div class="readonly">● SHADOW ONLY · NO PRODUCTION WRITES</div>
</header>
{primary}
{secondary}
{body}
<footer>QuantLab remains isolated from production registration and bankroll. This UI is read-only. Times are Europe/Belgrade.</footer>
</main>{NOTE_DIALOG_HTML}</body></html>"""


def _active_rows_html(
    rows: tuple[dict[str, Any], ...],
    *,
    lab_key: str,
    notes: dict[str, str],
) -> str:
    rendered = []
    for row in rows:
        note_cell = (
            f'<td class="notes-cell">{notes.get(_pick_id(row), "—")}</td>'
            if lab_key in {"goal", "card"}
            else ""
        )
        rendered.append(
            "<tr>"
            + _match_html(row, lab_key=lab_key)
            + f'<td><b>{escape(_pick_text(row))}</b></td>'
            + f"<td>{_bookmaker(row.get('bookmaker_name'))}</td>"
            + f"<td>{_pct(row.get('model_probability'))}<small>market {_pct(row.get('market_probability'))}</small></td>"
            + f"<td>{_odd(row.get('odds'))}</td>"
            + f"<td>{_pct(row.get('edge'), signed=True)}</td>"
            + f"<td>{_pct(row.get('expected_value'), signed=True)}</td>"
            + note_cell
            + f"<td>{_result_badge('PENDING')}</td>"
            + f"<td>{_time(row.get('decision_at'))}</td>"
            + "</tr>"
        )
    if not rendered:
        colspan = 10 if lab_key in {"goal", "card"} else 9
        return f'<tr><td class="empty" colspan="{colspan}">No active picks.</td></tr>'
    return "".join(rendered)


def _history_rows_html(
    rows: tuple[dict[str, Any], ...],
    *,
    lab_key: str,
    currency: str,
    notes: dict[str, str],
) -> str:
    rendered = []
    for row in rows:
        result = _result(row)
        pnl_raw = row.get("pnl_minor")
        pnl = None if pnl_raw is None else int(pnl_raw)
        pnl_class = "positive" if (pnl or 0) > 0 else "negative" if (pnl or 0) < 0 else "neutral"
        note_cell = (
            f'<td class="notes-cell">{notes.get(_pick_id(row), "—")}</td>'
            if lab_key in {"goal", "card"}
            else ""
        )
        rendered.append(
            "<tr>"
            + _match_html(row, lab_key=lab_key)
            + f'<td><b>{escape(_pick_text(row))}</b></td>'
            + f"<td>{_bookmaker(row.get('bookmaker_name'))}</td>"
            + f"<td>{_odd(row.get('odds'))}</td>"
            + note_cell
            + f"<td>{_result_badge(result)}</td>"
            + f'<td class="{pnl_class}">{_money(pnl, currency)}</td>'
            + f"<td>{_time(row.get('settled_at'))}</td>"
            + "</tr>"
        )
    if not rendered:
        colspan = 8 if lab_key in {"goal", "card"} else 7
        return f'<tr><td class="empty" colspan="{colspan}">No settled picks yet.</td></tr>'
    return "".join(rendered)


def render_dashboard(
    repository: Any,
    *,
    lab_key: str,
    api_daily_limit: int,
    currency: str,
) -> str:
    lab, title, subtitle = LABS[lab_key]
    warning = ""
    try:
        rows = _sorted(_display_rows(repository, lab))
    except Exception:  # noqa: BLE001 - dashboard must degrade on repository read failures
        rows = ()
        warning = (
            '<p class="analytics-note">Pick ledger temporarily unavailable. '
            'QuantLab processing is unchanged; this is a read-only dashboard error.</p>'
        )

    try:
        if lab == "GOAL":
            loader = getattr(repository, "list_all_goal_picks", None)
            metric_rows = _sorted(tuple(loader())) if callable(loader) else rows
        else:
            loader = getattr(repository, "list_all_bets", None)
            metric_rows = _sorted(tuple(loader(lab))) if callable(loader) else rows
    except Exception:  # noqa: BLE001 - dashboard must degrade on repository read failures
        metric_rows = rows
        if not warning:
            warning = (
                '<p class="analytics-note">Complete metric history temporarily unavailable. '
                'Visible picks remain available; QuantLab processing is unchanged.</p>'
            )

    active = tuple(row for row in rows if _result(row) == "PENDING")
    history = tuple(row for row in rows if _result(row) in {"WIN", "LOSS", "VOID"})
    metric_active = tuple(row for row in metric_rows if _result(row) == "PENDING")
    metric_history = tuple(
        row for row in metric_rows if _result(row) in {"WIN", "LOSS", "VOID"}
    )

    notes = (
        _goal_notes(repository, rows)
        if lab == "GOAL"
        else _card_notes(rows)
        if lab == "CARD"
        else {}
    )

    wins = sum(_result(row) == "WIN" for row in metric_history)
    losses = sum(_result(row) == "LOSS" for row in metric_history)
    voids = sum(_result(row) == "VOID" for row in metric_history)
    pnl = sum(int(row.get("pnl_minor") or 0) for row in metric_history)
    risked = sum(
        int(row.get("stake_minor") or 0)
        for row in metric_history
        if _result(row) in {"WIN", "LOSS"}
    )
    roi = None if risked == 0 else pnl / risked
    try:
        api_used = int(repository.api_usage_today())
    except Exception:  # noqa: BLE001 - dashboard must degrade on repository read failures
        api_used = 0

    cards = (
        ("Active picks", str(len(metric_active))),
        ("Settled", str(len(metric_history))),
        ("Wins", str(wins)),
        ("Losses", str(losses)),
        ("Voids", str(voids)),
        ("P&L", _money(pnl, currency)),
        ("ROI", "—" if roi is None else f"{roi * 100:+.2f}%"),
        ("QuantLab API", f"{api_used:,} / {api_daily_limit:,}"),
    )
    cards_html = "".join(
        f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
        for label, value in cards
    )

    body = (
        warning
        + f'<section class="cards">{cards_html}</section>'
        '<section class="panel">'
        '<div class="panel-title"><b>Active Picks</b>'
        f'<span>{len(active)} pending settlement</span></div>'
        '<div class="table"><table><thead><tr>'
        '<th>Match</th><th>Pick</th><th>Bookmaker</th><th>Model / market</th>'
        '<th>Odds</th><th>Edge</th><th>EV</th>'
        + ('<th>Notes</th>' if lab_key in {"goal", "card"} else '')
        + '<th>Status</th><th>Decision</th>'
        f'</tr></thead><tbody>{_active_rows_html(active, lab_key=lab_key, notes=notes)}</tbody></table></div>'
        '</section>'
        '<section class="panel">'
        '<div class="panel-title"><b>Pick History</b>'
        f'<span>{len(history)} settled · WIN / LOSS / VOID</span></div>'
        '<div class="table"><table><thead><tr>'
        '<th>Match</th><th>Pick</th><th>Bookmaker</th><th>Odds</th>'
        + ('<th>Notes</th>' if lab_key in {"goal", "card"} else '')
        + '<th>Result</th><th>P/L</th><th>Settled</th>'
        f'</tr></thead><tbody>{_history_rows_html(history, lab_key=lab_key, currency=currency, notes=notes)}</tbody></table></div>'
        '</section>'
    )
    return _shell(
        title=title,
        subtitle=subtitle,
        view="dashboard",
        lab_key=lab_key,
        body=body,
    )


def _probability_bucket(value: Any, *, market: bool = False) -> str:
    number = _number(value)
    if number is None:
        return "—"
    pct = number * 100
    ranges = (
        ((25, 35), (35, 40), (40, 45), (45, 50), (50, 55), (55, 60), (60, 65), (65, 75))
        if market
        else ((40, 45), (45, 50), (50, 55), (55, 60), (60, 65), (65, 70), (70, 75))
    )
    floor = 25 if market else 40
    for low, high in ranges:
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 75:
        return "75%+"
    return f"<{floor}%"


def _ev_bucket(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "—"
    pct = number * 100
    for low, high in ((0, 5), (5, 7), (7, 10), (10, 15), (15, 20), (20, 30)):
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 30:
        return "30%+"
    return "<0%"


def _edge_bucket(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "—"
    pct = number * 100
    for low, high in ((0, 5), (5, 7), (7, 10), (10, 15), (15, 20)):
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 20:
        return "20%+"
    return "<0%"


def _odds_bucket(value: Any) -> str:
    odds = _number(value)
    if odds is None:
        return "—"
    if odds < 1.40:
        return "<1.40"
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
    return "3.51+"


def _realized_clv_pct(row: dict[str, Any]) -> float | None:
    odds = row.get("odds")
    closing = row.get("closing_odds")
    entry_at = row.get("quote_observed_at")
    closing_at = row.get("closing_observed_at")
    if (
        odds is None
        or closing is None
        or not isinstance(entry_at, datetime)
        or not isinstance(closing_at, datetime)
        or closing_at <= entry_at
    ):
        return None
    return realized_clv_ppm(
        Decimal(str(odds)),
        Decimal(str(closing)),
    ) / 10_000.0


def _clv_bucket(row: dict[str, Any]) -> str:
    value = _realized_clv_pct(row)
    if value is None:
        return "—"
    for low, high in ((-10, -5), (-5, -2), (-2, 0), (0, 2), (2, 5), (5, 10)):
        if low <= value < high:
            return f"{low:+g}–{high:+g}%"
    if value < -10:
        return "<-10%"
    return "+10%+"


def _scalar_bucket(
    value: Any,
    *,
    breaks: tuple[float, ...],
    suffix: str = "",
    digits: int = 1,
) -> str:
    number = _number(value)
    if number is None:
        return "—"

    def fmt(item: float) -> str:
        return f"{item:.{digits}f}".rstrip("0").rstrip(".") + suffix

    if number < breaks[0]:
        return f"<{fmt(breaks[0])}"
    for low, high in pairwise(breaks):
        if low <= number < high:
            return f"{fmt(low)}–{fmt(high)}"
    return f"{fmt(breaks[-1])}+"


def _signed_gap_bucket(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "—"
    for low, high in ((-2, -1), (-1, -0.5), (-0.5, 0), (0, 0.5), (0.5, 1), (1, 2)):
        if low <= number < high:
            return f"{low:+g}–{high:+g}"
    if number < -2:
        return "<-2"
    return "+2+"


def _line_bucket(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:g}"


def _decision_lead_bucket(row: dict[str, Any]) -> str:
    kickoff = row.get("kickoff_at")
    decision = row.get("decision_at")
    if not isinstance(kickoff, datetime) or not isinstance(decision, datetime):
        return "—"
    hours = (kickoff - decision).total_seconds() / 3600
    if hours < 0:
        return "<0h"
    for low, high in ((0, 1), (1, 3), (3, 6), (6, 12), (12, 24), (24, 48)):
        if low <= hours < high:
            return f"{low:g}–{high:g}h"
    return "48h+"


def _quote_age_bucket(row: dict[str, Any]) -> str:
    quote = row.get("quote_observed_at")
    decision = row.get("decision_at")
    if not isinstance(quote, datetime) or not isinstance(decision, datetime):
        return "—"
    minutes = (decision - quote).total_seconds() / 60
    if minutes < 0:
        return "<0m"
    for low, high, label in (
        (0, 5, "0–5m"),
        (5, 15, "5–15m"),
        (15, 30, "15–30m"),
        (30, 60, "30–60m"),
        (60, 180, "1–3h"),
    ):
        if low <= minutes < high:
            return label
    return "3h+"


def _kickoff_dimensions(row: dict[str, Any]) -> tuple[str, str, str]:
    kickoff = row.get("kickoff_at")
    if not isinstance(kickoff, datetime):
        return "—", "—", "—"
    if kickoff.tzinfo is None or kickoff.utcoffset() is None:
        kickoff = kickoff.replace(tzinfo=UTC)
    local = kickoff.astimezone(BELGRADE)
    iso_year, iso_week, _ = local.isocalendar()
    hour = local.hour
    if hour < 6:
        daypart = "00–05"
    elif hour < 12:
        daypart = "06–11"
    elif hour < 18:
        daypart = "12–17"
    else:
        daypart = "18–23"
    return local.strftime("%A"), daypart, f"{iso_year}-W{iso_week:02d}"


def _raw_features(row: dict[str, Any], payload_key: str) -> dict[str, Any]:
    payload = row.get(payload_key)
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("raw_features")
    return raw if isinstance(raw, dict) else {}


def _feature_bucket(value: Any, kind: str) -> str:
    if kind == "goals":
        return _scalar_bucket(
            value,
            breaks=(0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0),
        )
    if kind == "corners":
        return _scalar_bucket(
            value,
            breaks=(2, 3, 4, 5, 6, 7, 8, 9),
            digits=0,
        )
    if kind == "shots":
        return _scalar_bucket(
            value,
            breaks=(6, 8, 10, 12, 14, 16, 20),
            digits=0,
        )
    if kind == "sot":
        return _scalar_bucket(
            value,
            breaks=(2, 3, 4, 5, 6, 7, 8),
            digits=0,
        )
    return "—"


def _mean_available(*values: Any) -> float | None:
    numbers = [number for value in values if (number := _number(value)) is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _first_number(*values: Any) -> float | None:
    for value in values:
        number = _number(value)
        if number is not None:
            return number
    return None


def _difference(left: Any, right: Any) -> float | None:
    left_number = _number(left)
    right_number = _number(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def _feature_missingness_bucket(raw: dict[str, Any]) -> str:
    candidates = [
        value
        for key, value in raw.items()
        if not key.endswith("__missing")
    ]
    if not candidates:
        return "—"
    missing = sum(_number(value) is None for value in candidates)
    pct = missing / len(candidates) * 100
    return _scalar_bucket(
        pct,
        breaks=(1, 5, 10, 20, 30, 50),
        suffix="%",
        digits=0,
    )


def _history_depth_bucket(row: dict[str, Any], raw: dict[str, Any]) -> str:
    home = _first_number(
        row.get("home_history_size"),
        raw.get("home_history_match_count"),
        raw.get("home_season_match_count"),
        raw.get("home_history_n"),
    )
    away = _first_number(
        row.get("away_history_size"),
        raw.get("away_history_match_count"),
        raw.get("away_season_match_count"),
        raw.get("away_history_n"),
    )
    if home is None or away is None:
        return "—"
    return _scalar_bucket(
        min(home, away),
        breaks=(5, 10, 20, 30, 50),
        digits=0,
    )


def _balance_bucket(smaller: float | None, larger: float | None) -> str:
    if smaller is None or larger is None or larger <= 0:
        return "—"
    ratio_pct = smaller / larger * 100
    return _scalar_bucket(
        ratio_pct,
        breaks=(25, 50, 70, 85, 95),
        suffix="%",
        digits=0,
    )


def _trend_bucket(raw: dict[str, Any], metric: str) -> str:
    home = _difference(
        raw.get(f"home_l5_{metric}"),
        raw.get(f"home_l10_{metric}"),
    )
    away = _difference(
        raw.get(f"away_l5_{metric}"),
        raw.get(f"away_l10_{metric}"),
    )
    return _signed_gap_bucket(_mean_available(home, away))


def _venue_trend_bucket(raw: dict[str, Any], metric: str) -> str:
    home = _difference(
        raw.get(f"home_venue_l5_{metric}"),
        raw.get(f"home_l10_{metric}"),
    )
    away = _difference(
        raw.get(f"away_venue_l5_{metric}"),
        raw.get(f"away_l10_{metric}"),
    )
    return _signed_gap_bucket(_mean_available(home, away))


def _goal_matchup_pressure_bucket(raw: dict[str, Any]) -> str:
    home_matchup = _mean_available(
        raw.get("home_l5_goals_for"),
        raw.get("away_l5_goals_against"),
    )
    away_matchup = _mean_available(
        raw.get("away_l5_goals_for"),
        raw.get("home_l5_goals_against"),
    )
    total = (
        None
        if home_matchup is None or away_matchup is None
        else home_matchup + away_matchup
    )
    return _scalar_bucket(
        total,
        breaks=(1.5, 2.0, 2.5, 3.0, 3.5, 4.0),
    )


def _corner_matchup_pressure_bucket(raw: dict[str, Any]) -> str:
    home_matchup = _mean_available(
        raw.get("home_l5_corners_for"),
        raw.get("away_l5_corners_against"),
    )
    away_matchup = _mean_available(
        raw.get("away_l5_corners_for"),
        raw.get("home_l5_corners_against"),
    )
    total = (
        None
        if home_matchup is None or away_matchup is None
        else home_matchup + away_matchup
    )
    return _scalar_bucket(
        total,
        breaks=(7, 8, 9, 10, 11, 12, 13, 14),
        digits=0,
    )


def _corner_calibration_watch_bucket(row: dict[str, Any]) -> str:
    """Research-only CornerLab regimes motivated by repeated line-calibration bias."""
    selection = str(row.get("selection") or "").upper()
    line = _number(row.get("line"))
    model_probability = _number(row.get("model_probability"))

    if selection == "UNDER" and line is not None and 7.5 <= line <= 10.5:
        return "UNDER mid-lines 7.5–10.5"
    if (
        selection == "OVER"
        and model_probability is not None
        and 0.60 <= model_probability < 0.70
    ):
        return "OVER model P 60–70%"
    if selection == "OVER" and line is not None and 12.5 <= line <= 13.5:
        return "OVER high-lines 12.5–13.5"
    return "—"


def _watchlist_block(content: str, *, lab_key: str) -> str:
    if not content:
        return ""
    focus = (
        "λ shape · price · trend · matchup · reliability"
        if lab_key == "goal"
        else "calibration regimes · model-line gap · price · pressure trend · matchup · reliability"
        if lab_key == "corner"
        else "raw consensus · referee · team discipline · fouls · context · cross-buckets"
    )
    return (
        '<section class="watchlist" id="analytics-watchlist">'
        '<div class="watchlist-head"><b>Watchlist · ROI discovery</b>'
        f'<span>{escape(focus)} · pre-match features only</span></div>'
        + content
        + "</section>"
    )


def _analytics_row(row: dict[str, Any], *, lab_key: str) -> dict[str, Any]:
    item = dict(row)
    weekday, daypart, week = _kickoff_dimensions(item)
    item.update(
        {
            "model_probability_bucket": _probability_bucket(item.get("model_probability")),
            "market_probability_bucket": _probability_bucket(
                item.get("market_probability"),
                market=True,
            ),
            "edge_bucket": _edge_bucket(item.get("edge")),
            "ev_bucket": _ev_bucket(item.get("expected_value")),
            "entry_odds_bucket": _odds_bucket(item.get("odds")),
            "closing_odds_bucket": _odds_bucket(item.get("closing_odds")),
            "clv_bucket": _clv_bucket(item),
            "line_bucket": _line_bucket(item.get("line")),
            "decision_lead_bucket": _decision_lead_bucket(item),
            "quote_age_bucket": _quote_age_bucket(item),
            "kickoff_weekday": weekday,
            "kickoff_time_bucket": daypart,
            "kickoff_week": week,
        }
    )
    payload_key = (
        "feature_payload"
        if lab_key == "goal"
        else "corner_feature_payload"
        if lab_key == "corner"
        else "card_feature_payload"
    )
    raw_for_reliability = _raw_features(item, payload_key)
    item.update(
        {
            "history_depth_bucket": _history_depth_bucket(item, raw_for_reliability),
            "feature_missingness_bucket": _feature_missingness_bucket(raw_for_reliability),
        }
    )
    if lab_key == "goal":
        home = _number(item.get("expected_home_goals"))
        away = _number(item.get("expected_away_goals"))
        total = None if home is None or away is None else home + away
        raw = _raw_features(item, "feature_payload")
        edge = _number(item.get("edge"))
        ev = _number(item.get("expected_value"))
        extreme = (ev is not None and ev >= 0.30) or (edge is not None and edge >= 0.20)
        low_scoring = (
            item.get("market_key") == "OU_25" and item.get("selection") == "UNDER"
        ) or (
            item.get("market_key") == "BTTS" and item.get("selection") == "NO"
        )
        diagnostic = (
            "LOW_SCORING_EXTREME"
            if low_scoring and extreme
            else "LOW_SCORING_NON_EXTREME"
            if low_scoring
            else "OTHER_EXTREME"
            if extreme
            else "OTHER_NON_EXTREME"
        )
        item.update(
            {
                "goal_diagnostic_bucket": diagnostic,
                "expected_total_goals_bucket": _scalar_bucket(
                    total,
                    breaks=(1.5, 2.0, 2.5, 3.0, 3.5, 4.0),
                ),
                "expected_home_goals_bucket": _scalar_bucket(
                    home,
                    breaks=(0.5, 1.0, 1.5, 2.0, 2.5),
                ),
                "expected_away_goals_bucket": _scalar_bucket(
                    away,
                    breaks=(0.5, 1.0, 1.5, 2.0, 2.5),
                ),
                "goal_lambda_spread_bucket": _signed_gap_bucket(
                    None if home is None or away is None else home - away
                ),
                "goal_lambda_min_bucket": _scalar_bucket(
                    None if home is None or away is None else min(home, away),
                    breaks=(0.4, 0.7, 1.0, 1.3, 1.6, 2.0),
                ),
                "goal_lambda_max_bucket": _scalar_bucket(
                    None if home is None or away is None else max(home, away),
                    breaks=(0.8, 1.2, 1.6, 2.0, 2.5, 3.0),
                ),
                "goal_lambda_balance_bucket": _balance_bucket(
                    None if home is None or away is None else min(home, away),
                    None if home is None or away is None else max(home, away),
                ),
                "goal_total_line_gap_bucket": _signed_gap_bucket(
                    None
                    if total is None or _number(item.get("line")) is None
                    else total - float(item["line"])
                ),
                "goal_attack_trend_bucket": _trend_bucket(raw, "goals_for"),
                "goal_venue_trend_bucket": _venue_trend_bucket(raw, "goals_for"),
                "goal_shot_trend_bucket": _trend_bucket(raw, "shots_for"),
                "goal_sot_trend_bucket": _trend_bucket(raw, "sot_for"),
                "goal_matchup_pressure_bucket": _goal_matchup_pressure_bucket(raw),
                "feature_home_l5_goals_for_bucket": _feature_bucket(
                    raw.get("home_l5_goals_for"), "goals"
                ),
                "feature_home_l5_goals_against_bucket": _feature_bucket(
                    raw.get("home_l5_goals_against"), "goals"
                ),
                "feature_away_l5_goals_for_bucket": _feature_bucket(
                    raw.get("away_l5_goals_for"), "goals"
                ),
                "feature_away_l5_goals_against_bucket": _feature_bucket(
                    raw.get("away_l5_goals_against"), "goals"
                ),
                "feature_home_l5_shots_for_bucket": _feature_bucket(
                    raw.get("home_l5_shots_for"), "shots"
                ),
                "feature_away_l5_shots_for_bucket": _feature_bucket(
                    raw.get("away_l5_shots_for"), "shots"
                ),
                "feature_home_l5_sot_for_bucket": _feature_bucket(
                    raw.get("home_l5_sot_for"), "sot"
                ),
                "feature_away_l5_sot_for_bucket": _feature_bucket(
                    raw.get("away_l5_sot_for"), "sot"
                ),
            }
        )
    elif lab_key == "corner":
        expected = _number(item.get("expected_total_corners"))
        line = _number(item.get("line"))
        raw = _raw_features(item, "corner_feature_payload")
        item.update(
            {
                "expected_total_corners_bucket": _scalar_bucket(
                    expected,
                    breaks=(7, 8, 9, 10, 11, 12, 13),
                    digits=0,
                ),
                "corner_calibration_watch_bucket": _corner_calibration_watch_bucket(item),
                "corner_model_line_gap_bucket": _signed_gap_bucket(
                    None if expected is None or line is None else expected - line
                ),
                "corner_trend_bucket": _trend_bucket(raw, "corners_for"),
                "corner_venue_trend_bucket": _venue_trend_bucket(raw, "corners_for"),
                "corner_shot_trend_bucket": _trend_bucket(raw, "shots_for"),
                "corner_sot_trend_bucket": _trend_bucket(raw, "sot_for"),
                "corner_matchup_pressure_bucket": _corner_matchup_pressure_bucket(raw),
                "feature_home_l5_corners_for_bucket": _feature_bucket(
                    raw.get("home_l5_corners_for"), "corners"
                ),
                "feature_home_l5_corners_against_bucket": _feature_bucket(
                    raw.get("home_l5_corners_against"), "corners"
                ),
                "feature_away_l5_corners_for_bucket": _feature_bucket(
                    raw.get("away_l5_corners_for"), "corners"
                ),
                "feature_away_l5_corners_against_bucket": _feature_bucket(
                    raw.get("away_l5_corners_against"), "corners"
                ),
                "feature_home_l5_shots_for_bucket": _feature_bucket(
                    raw.get("home_l5_shots_for"), "shots"
                ),
                "feature_away_l5_shots_for_bucket": _feature_bucket(
                    raw.get("away_l5_shots_for"), "shots"
                ),
                "feature_home_l5_sot_for_bucket": _feature_bucket(
                    raw.get("home_l5_sot_for"), "sot"
                ),
                "feature_away_l5_sot_for_bucket": _feature_bucket(
                    raw.get("away_l5_sot_for"), "sot"
                ),
            }
        )
    elif lab_key == "card":
        raw = _raw_features(item, "card_feature_payload")
        details = item.get("decision_details")
        details = details if isinstance(details, dict) else {}
        signal = details.get("raw_signal")
        signal = signal if isinstance(signal, dict) else {}

        def scalar(name: str, breaks: tuple[float, ...], *, suffix: str = "", digits: int = 1) -> str:
            return _scalar_bucket(raw.get(name), breaks=breaks, suffix=suffix, digits=digits)

        def pct_scalar(name: str) -> str:
            value = _number(raw.get(name))
            return _scalar_bucket(
                None if value is None else value * 100.0,
                breaks=(20, 40, 50, 60, 70, 80, 90),
                suffix="%",
                digits=0,
            )

        consensus = _first_number(signal.get("consensus_cards"), raw.get("raw_consensus_cards"))
        line = _number(item.get("line"))
        signal_gap = _first_number(
            signal.get("line_gap"),
            None if consensus is None or line is None else consensus - line,
        )
        directional_support = _number(signal.get("directional_support"))
        observed_hit = _number(signal.get("observed_hit_rate"))
        anchor_count = _first_number(signal.get("anchor_count"), raw.get("raw_anchor_count"))

        item.update(
            {
                "card_raw_policy_bucket": (
                    "RAW_STATS"
                    if str(item.get("policy_version") or "").startswith("CARDLAB_RAW_STATS_POLICY_")
                    else "LEGACY_VALUE"
                ),
                "card_raw_consensus_bucket": _scalar_bucket(
                    consensus, breaks=(3, 4, 4.5, 5, 5.5, 6, 7, 8), digits=1
                ),
                "card_raw_line_gap_bucket": _signed_gap_bucket(signal_gap),
                "card_raw_support_bucket": _scalar_bucket(
                    None if directional_support is None else directional_support * 100,
                    breaks=(50, 60, 67, 75, 80, 90),
                    suffix="%",
                    digits=0,
                ),
                "card_raw_hit_rate_bucket": _scalar_bucket(
                    None if observed_hit is None else observed_hit * 100,
                    breaks=(40, 50, 55, 60, 67, 75, 80),
                    suffix="%",
                    digits=0,
                ),
                "card_raw_anchor_count_bucket": _scalar_bucket(
                    anchor_count, breaks=(2, 3, 4, 5, 6, 7), digits=0
                ),
                "card_referee_cards_l5_bucket": scalar(
                    "referee_l5_cards", (3, 4, 4.5, 5, 5.5, 6, 7), digits=1
                ),
                "card_referee_cards_l10_bucket": scalar(
                    "referee_l10_cards", (3, 4, 4.5, 5, 5.5, 6, 7), digits=1
                ),
                "card_referee_yellows_l10_bucket": scalar(
                    "referee_l10_yellows", (2, 3, 4, 5, 6, 7), digits=1
                ),
                "card_referee_reds_l10_bucket": scalar(
                    "referee_l10_reds", (0.05, 0.15, 0.25, 0.4, 0.6, 1.0), digits=2
                ),
                "card_referee_fouls_l10_bucket": scalar(
                    "referee_l10_fouls", (18, 22, 26, 30, 34, 38, 42), digits=0
                ),
                "card_referee_cards_per_foul_bucket": scalar(
                    "referee_l10_cards_per_foul", (0.10, 0.14, 0.18, 0.22, 0.26, 0.30), digits=2
                ),
                "card_referee_home_bias_bucket": _signed_gap_bucket(
                    raw.get("referee_home_away_bias_l10")
                ),
                "card_referee_over35_bucket": pct_scalar("referee_over_3_5_rate_l10"),
                "card_referee_over45_bucket": pct_scalar("referee_over_4_5_rate_l10"),
                "card_referee_over55_bucket": pct_scalar("referee_over_5_5_rate_l10"),
                "card_home_cards_l5_bucket": scalar(
                    "home_l5_cards_for", (1, 1.5, 2, 2.5, 3, 3.5, 4), digits=1
                ),
                "card_home_cards_l10_bucket": scalar(
                    "home_l10_cards_for", (1, 1.5, 2, 2.5, 3, 3.5, 4), digits=1
                ),
                "card_away_cards_l5_bucket": scalar(
                    "away_l5_cards_for", (1, 1.5, 2, 2.5, 3, 3.5, 4), digits=1
                ),
                "card_away_cards_l10_bucket": scalar(
                    "away_l10_cards_for", (1, 1.5, 2, 2.5, 3, 3.5, 4), digits=1
                ),
                "card_home_cards_against_l10_bucket": scalar(
                    "home_l10_cards_against", (1, 1.5, 2, 2.5, 3, 3.5, 4), digits=1
                ),
                "card_away_cards_against_l10_bucket": scalar(
                    "away_l10_cards_against", (1, 1.5, 2, 2.5, 3, 3.5, 4), digits=1
                ),
                "card_home_fouls_l10_bucket": scalar(
                    "home_l10_fouls_committed", (8, 10, 12, 14, 16, 18, 20), digits=0
                ),
                "card_away_fouls_l10_bucket": scalar(
                    "away_l10_fouls_committed", (8, 10, 12, 14, 16, 18, 20), digits=0
                ),
                "card_home_fouls_suffered_l10_bucket": scalar(
                    "home_l10_fouls_suffered", (8, 10, 12, 14, 16, 18, 20), digits=0
                ),
                "card_away_fouls_suffered_l10_bucket": scalar(
                    "away_l10_fouls_suffered", (8, 10, 12, 14, 16, 18, 20), digits=0
                ),
                "card_home_cards_per_foul_bucket": scalar(
                    "home_l10_cards_per_foul", (0.08, 0.12, 0.16, 0.20, 0.24, 0.30), digits=2
                ),
                "card_away_cards_per_foul_bucket": scalar(
                    "away_l10_cards_per_foul", (0.08, 0.12, 0.16, 0.20, 0.24, 0.30), digits=2
                ),
                "card_home_venue_cards_bucket": scalar(
                    "home_venue_l5_cards_for", (1, 1.5, 2, 2.5, 3, 3.5, 4), digits=1
                ),
                "card_away_venue_cards_bucket": scalar(
                    "away_venue_l5_cards_for", (1, 1.5, 2, 2.5, 3, 3.5, 4), digits=1
                ),
                "card_home_2plus_bucket": pct_scalar("home_cards_2plus_rate_l10"),
                "card_home_3plus_bucket": pct_scalar("home_cards_3plus_rate_l10"),
                "card_home_4plus_bucket": pct_scalar("home_cards_4plus_rate_l10"),
                "card_away_2plus_bucket": pct_scalar("away_cards_2plus_rate_l10"),
                "card_away_3plus_bucket": pct_scalar("away_cards_3plus_rate_l10"),
                "card_away_4plus_bucket": pct_scalar("away_cards_4plus_rate_l10"),
                "card_combined_cards_l5_bucket": scalar(
                    "combined_team_cards_for_l5", (3, 4, 4.5, 5, 5.5, 6, 7), digits=1
                ),
                "card_combined_cards_l10_bucket": scalar(
                    "combined_team_cards_for_l10", (3, 4, 4.5, 5, 5.5, 6, 7), digits=1
                ),
                "card_combined_fouls_l10_bucket": scalar(
                    "combined_fouls_committed_l10", (18, 22, 26, 30, 34, 38, 42), digits=0
                ),
                "card_matchup_cards_bucket": scalar(
                    "matchup_expected_cards_l10", (3, 4, 4.5, 5, 5.5, 6, 7), digits=1
                ),
                "card_matchup_fouls_bucket": scalar(
                    "matchup_expected_fouls_l10", (18, 22, 26, 30, 34, 38, 42), digits=0
                ),
                "card_aggression_foul_draw_bucket": scalar(
                    "aggression_foul_draw_interaction", (1, 1.5, 2, 2.5, 3, 4), digits=1
                ),
                "card_h2h_total_bucket": scalar(
                    "h2h_total_cards_l5", (3, 4, 4.5, 5, 5.5, 6, 7), digits=1
                ),
                "card_h2h_n_bucket": scalar("h2h_n", (1, 2, 3, 4, 5), digits=0),
                "card_league_total_bucket": scalar(
                    "league_total_cards", (3, 4, 4.5, 5, 5.5, 6, 7), digits=1
                ),
                "card_referee_vs_league_bucket": _signed_gap_bucket(
                    raw.get("referee_vs_league_cards_delta")
                ),
                "card_referee_vs_teams_bucket": _signed_gap_bucket(
                    raw.get("referee_vs_teams_cards_delta")
                ),
                "card_home_league_percentile_bucket": pct_scalar(
                    "home_cards_for_league_percentile"
                ),
                "card_away_league_percentile_bucket": pct_scalar(
                    "away_cards_for_league_percentile"
                ),
                "card_home_foul_percentile_bucket": pct_scalar(
                    "home_fouls_league_percentile"
                ),
                "card_away_foul_percentile_bucket": pct_scalar(
                    "away_fouls_league_percentile"
                ),
                "card_stage_bucket": scalar(
                    "stage_of_season", (0.25, 0.50, 0.75, 0.90), digits=2
                ),
                "card_importance_bucket": scalar(
                    "match_importance", (0.25, 0.50, 0.65, 0.80, 0.90), digits=2
                ),
                "card_table_pressure_bucket": scalar(
                    "table_pressure", (0.25, 0.50, 0.65, 0.80, 0.90), digits=2
                ),
                "card_must_win_bucket": scalar(
                    "must_win_proxy", (0.20, 0.40, 0.60, 0.75, 0.90), digits=2
                ),
                "card_rank_gap_bucket": scalar("rank_gap", (2, 4, 6, 10, 15), digits=0),
                "card_points_gap_bucket": scalar("points_gap", (3, 6, 10, 15, 25), digits=0),
                "card_derby_bucket": (
                    "DERBY" if _number(raw.get("derby_rivalry_indicator")) == 1 else "NON_DERBY"
                    if _number(raw.get("derby_rivalry_indicator")) == 0 else "—"
                ),
                "card_cup_bucket": (
                    "CUP" if _number(raw.get("cup_indicator")) == 1 else "LEAGUE"
                    if _number(raw.get("cup_indicator")) == 0 else "—"
                ),
                "card_late_season_bucket": (
                    "LATE" if _number(raw.get("late_season_indicator")) == 1 else "EARLY_MID"
                    if _number(raw.get("late_season_indicator")) == 0 else "—"
                ),
                "card_similar_strength_bucket": (
                    "SIMILAR" if _number(raw.get("similar_strength_indicator")) == 1 else "UNEQUAL"
                    if _number(raw.get("similar_strength_indicator")) == 0 else "—"
                ),
                "card_favorite_probability_bucket": _scalar_bucket(
                    None
                    if _number(raw.get("market_favorite_fair_probability")) is None
                    else _number(raw.get("market_favorite_fair_probability")) * 100,
                    breaks=(40, 50, 60, 70, 80),
                    suffix="%",
                    digits=0,
                ),
                "card_1x2_balance_bucket": _scalar_bucket(
                    None
                    if _number(raw.get("market_one_x_two_balance")) is None
                    else _number(raw.get("market_one_x_two_balance")) * 100,
                    breaks=(50, 60, 70, 80, 90),
                    suffix="%",
                    digits=0,
                ),
                "card_goal_over25_bucket": _scalar_bucket(
                    None
                    if _number(raw.get("market_goals_over_2_5_fair_probability")) is None
                    else _number(raw.get("market_goals_over_2_5_fair_probability")) * 100,
                    breaks=(35, 45, 50, 55, 65, 75),
                    suffix="%",
                    digits=0,
                ),
                "card_btts_bucket": _scalar_bucket(
                    None
                    if _number(raw.get("market_btts_yes_fair_probability")) is None
                    else _number(raw.get("market_btts_yes_fair_probability")) * 100,
                    breaks=(35, 45, 50, 55, 65, 75),
                    suffix="%",
                    digits=0,
                ),
                "card_handicap_bucket": _signed_gap_bucket(
                    raw.get("market_favorite_handicap_line")
                ),
                "card_possession_imbalance_bucket": scalar(
                    "expected_possession_imbalance", (5, 10, 15, 20, 30), digits=0
                ),
                "card_cards_trend_bucket": _trend_bucket(raw, "cards_for"),
                "card_fouls_trend_bucket": _trend_bucket(raw, "fouls_committed"),
                "card_venue_cards_trend_bucket": _venue_trend_bucket(raw, "cards_for"),
            }
        )
    return item


def _analytics_rows(
    rows: tuple[dict[str, Any], ...],
    *,
    lab_key: str,
) -> tuple[dict[str, Any], ...]:
    enriched = [_analytics_row(row, lab_key=lab_key) for row in rows]
    if lab_key == "card":
        counts: dict[str, int] = defaultdict(int)
        for row in enriched:
            counts[str(row.get("fixture_id") or "")] += 1
        for row in enriched:
            count = counts[str(row.get("fixture_id") or "")]
            row["card_fixture_pick_count_bucket"] = (
                "1" if count == 1 else "2" if count == 2 else "3+"
            )
    return tuple(enriched)


def _dimension_available(
    rows: tuple[dict[str, Any], ...],
    dimensions: tuple[str, ...],
) -> bool:
    return any(
        all(str(row.get(dimension) or "—") != "—" for dimension in dimensions)
        for row in rows
    )


def _analytics_section(title: str, subtitle: str) -> str:
    return (
        f'<h2 class="analytics-section">{escape(title)}'
        f'<small>{escape(subtitle)}</small></h2>'
    )


def _cohorts(
    rows: tuple[dict[str, Any], ...],
    dimensions: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(str(row.get(dimension) or "—") for dimension in dimensions)
        grouped[key].append(row)
    output = []
    for key, cohort in grouped.items():
        item = {
            dimension: value
            for dimension, value in zip(dimensions, key, strict=True)
        }
        item.update(goal_pick_metrics(cohort))
        output.append(item)
    return tuple(
        sorted(
            output,
            key=lambda item: (
                -int(item["graded_n"]),
                *(str(item[dimension]) for dimension in dimensions),
            ),
        )
    )


def _metric(value: Any, *, suffix: str = "", signed: bool = False, digits: int = 2) -> str:
    if value is None:
        return "—"
    number = float(value)
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.{digits}f}{suffix}"


def _param(
    params: dict[str, list[str]],
    name: str,
    default: str = "",
) -> str:
    values = params.get(name)
    if not values:
        return default
    return values[0].strip()


def _analytics_href(
    params: dict[str, list[str]],
    *,
    updates: dict[str, Any] | None = None,
    anchor: str = "",
    clear_prefixes: tuple[str, ...] = (),
) -> str:
    current = {
        key: values[0]
        for key, values in params.items()
        if values and values[0] != ""
    }
    for key in tuple(current):
        if any(
            key == prefix or key.startswith(prefix + "_")
            for prefix in clear_prefixes
        ):
            current.pop(key, None)
    for key, value in (updates or {}).items():
        if value is None or value == "":
            current.pop(key, None)
        else:
            current[key] = str(value)
    current["view"] = "analytics"
    href = "/quantlab?" + urlencode(current)
    return href + (f"#{anchor}" if anchor else "")


def _sortable_th(
    label: str,
    key: str,
    *,
    table_key: str,
    params: dict[str, list[str]],
    anchor: str,
    active_key: str,
    active_dir: str,
    first_dir: str,
) -> str:
    active = active_key == key
    next_dir = (
        ("desc" if active_dir == "asc" else "asc")
        if active
        else first_dir
    )
    href = _analytics_href(
        params,
        updates={
            f"{table_key}_sort": key,
            f"{table_key}_dir": next_dir,
        },
        anchor=anchor,
    )
    arrow = "↑" if active and active_dir == "asc" else "↓" if active else ""
    css = "sort-header active" if active else "sort-header"
    arrow_html = f'<span class="sort-arrow">{arrow}</span>' if arrow else ""
    return (
        f'<th><a class="{css}" href="{escape(href, quote=True)}">'
        f'{escape(label)}{arrow_html}</a></th>'
    )


def _bucket_sort_value(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text == "—":
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match is None:
        return None
    number = float(match.group(0))
    if text.startswith("<"):
        number -= 0.001
    return number


def _cohort_sort_value(row: dict[str, Any], key: str) -> Any:
    if key == "record":
        return (
            int(row.get("wins") or 0),
            -int(row.get("losses") or 0),
            -int(row.get("voids") or 0),
        )
    value = row.get(key)
    if value is None:
        return None
    if key == "kickoff_week":
        text = str(value)
        try:
            year, week = text.split("-W", 1)
            return int(year) * 100 + int(week)
        except (TypeError, ValueError):
            return None
    if key == "kickoff_weekday":
        return {
            "Monday": 1,
            "Tuesday": 2,
            "Wednesday": 3,
            "Thursday": 4,
            "Friday": 5,
            "Saturday": 6,
            "Sunday": 7,
        }.get(str(value))
    if key.endswith("_bucket") or key == "line_bucket":
        numeric = _bucket_sort_value(value)
        return numeric if numeric is not None else str(value).casefold()
    if key == "sample_band":
        return {
            "SIGNAL_ONLY": 0,
            "MONITOR": 1,
            "PROVISIONAL_EVIDENCE": 2,
            "STABILITY_REVIEW": 3,
        }.get(str(value), -1)
    if isinstance(value, (int, float)):
        return float(value)
    return str(value).casefold()


def _sort_cohort_rows(
    rows: tuple[dict[str, Any], ...],
    *,
    key: str,
    direction: str,
) -> tuple[dict[str, Any], ...]:
    populated = [row for row in rows if int(row.get("n") or 0) > 0]
    zero_sample = [row for row in rows if int(row.get("n") or 0) == 0]
    present = [row for row in populated if _cohort_sort_value(row, key) is not None]
    missing = [row for row in populated if _cohort_sort_value(row, key) is None]
    present.sort(
        key=lambda row: _cohort_sort_value(row, key),
        reverse=direction == "desc",
    )
    return tuple(present + missing + zero_sample)


def _cohort_table(
    title: str,
    rows: tuple[dict[str, Any], ...],
    dimensions: tuple[str, ...],
    *,
    lab_key: str,
    table_key: str,
    params: dict[str, list[str]],
    currency: str,
    dimension_labels: dict[str, str] | None = None,
) -> str:
    allowed_sort_keys = {
        *dimensions,
        "n",
        "record",
        "win_rate_pct",
        "expected_win_rate_pct",
        "calibration_gap_pp",
        "roi_pct",
        "pnl_minor",
        "avg_odds",
        "brier_score",
        "log_loss",
        "avg_clv_pct",
        "clv_n",
        "closing_coverage_pct",
        "max_drawdown_minor",
        "avg_edge_pct",
        "avg_ev_pct",
        "sample_band",
    }
    sort_key = _param(params, f"{table_key}_sort", "n")
    if sort_key not in allowed_sort_keys:
        sort_key = "n"
    sort_dir = _param(params, f"{table_key}_dir", "desc").casefold()
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    ordered_rows = _sort_cohort_rows(rows, key=sort_key, direction=sort_dir)
    anchor = f"analytics-{table_key}"

    headers = "".join(
        _sortable_th(
            (dimension_labels or {}).get(
                dimension,
                dimension.replace("_", " ").title(),
            ),
            dimension,
            table_key=table_key,
            params=params,
            anchor=anchor,
            active_key=sort_key,
            active_dir=sort_dir,
            first_dir="asc",
        )
        for dimension in dimensions
    )
    metric_headers = (
        (
            ("N", "n", "desc"),
            ("W-L-V", "record", "desc"),
            ("Win%", "win_rate_pct", "desc"),
            ("ROI", "roi_pct", "desc"),
            ("P/L", "pnl_minor", "desc"),
            ("Avg odds", "avg_odds", "desc"),
            ("Avg CLV", "avg_clv_pct", "desc"),
            ("CLV N", "clv_n", "desc"),
            ("CLV cov", "closing_coverage_pct", "desc"),
            ("Max DD", "max_drawdown_minor", "asc"),
            ("Evidence", "sample_band", "asc"),
        )
        if lab_key == "card"
        else (
            ("N", "n", "desc"),
            ("W-L-V", "record", "desc"),
            ("Win%", "win_rate_pct", "desc"),
            ("Exp%", "expected_win_rate_pct", "desc"),
            ("Cal gap", "calibration_gap_pp", "desc"),
            ("ROI", "roi_pct", "desc"),
            ("P/L", "pnl_minor", "desc"),
            ("Avg odds", "avg_odds", "desc"),
            ("Brier", "brier_score", "asc"),
            ("Log loss", "log_loss", "asc"),
            ("Avg CLV", "avg_clv_pct", "desc"),
            ("CLV N", "clv_n", "desc"),
            ("CLV cov", "closing_coverage_pct", "desc"),
            ("Max DD", "max_drawdown_minor", "asc"),
            ("Avg edge", "avg_edge_pct", "desc"),
            ("Avg EV", "avg_ev_pct", "desc"),
            ("Evidence", "sample_band", "asc"),
        )
    )
    headers += "".join(
        _sortable_th(
            label,
            key,
            table_key=table_key,
            params=params,
            anchor=anchor,
            active_key=sort_key,
            active_dir=sort_dir,
            first_dir=first_dir,
        )
        for label, key, first_dir in metric_headers
    )

    rendered = []
    for row in ordered_rows:
        bucket_updates = {
            "bucket": "1",
            **{
                f"bucket_{dimension}": str(row.get(dimension) or "—")
                for dimension in dimensions
            },
        }
        href = _analytics_href(
            params,
            updates=bucket_updates,
            anchor="bucket-picks",
            clear_prefixes=("bucket",),
        )
        dimension_cells = "".join(
            f'<td><a class="group-link" href="{escape(href, quote=True)}">'
            f'{escape(str(row.get(dimension) or "—"))}</a></td>'
            for dimension in dimensions
        )
        pnl = row.get("pnl_minor")
        max_dd = row.get("max_drawdown_minor")
        if lab_key == "card":
            metric_cells = (
                f"<td>{row['n']}</td>"
                + f"<td>{row['wins']}-{row['losses']}-{row['voids']}</td>"
                + f"<td>{_metric(row['win_rate_pct'], suffix='%')}</td>"
                + f"<td>{_metric(row['roi_pct'], suffix='%', signed=True)}</td>"
                + f"<td>{_money(None if pnl is None else int(pnl), currency)}</td>"
                + f"<td>{_metric(row['avg_odds'], digits=2)}</td>"
                + f"<td>{_metric(row['avg_clv_pct'], suffix='%', signed=True)}</td>"
                + f"<td>{row['clv_n']}</td>"
                + f"<td>{_metric(row['closing_coverage_pct'], suffix='%')}</td>"
                + f"<td>{_money(None if max_dd is None else int(max_dd), currency)}</td>"
                + f"<td>{escape(str(row['sample_band']))}</td>"
            )
        else:
            metric_cells = (
                f"<td>{row['n']}</td>"
                + f"<td>{row['wins']}-{row['losses']}-{row['voids']}</td>"
                + f"<td>{_metric(row['win_rate_pct'], suffix='%')}</td>"
                + f"<td>{_metric(row['expected_win_rate_pct'], suffix='%')}</td>"
                + f"<td>{_metric(row['calibration_gap_pp'], suffix='pp', signed=True)}</td>"
                + f"<td>{_metric(row['roi_pct'], suffix='%', signed=True)}</td>"
                + f"<td>{_money(None if pnl is None else int(pnl), currency)}</td>"
                + f"<td>{_metric(row['avg_odds'], digits=2)}</td>"
                + f"<td>{_metric(row['brier_score'], digits=3)}</td>"
                + f"<td>{_metric(row['log_loss'], digits=3)}</td>"
                + f"<td>{_metric(row['avg_clv_pct'], suffix='%', signed=True)}</td>"
                + f"<td>{row['clv_n']}</td>"
                + f"<td>{_metric(row['closing_coverage_pct'], suffix='%')}</td>"
                + f"<td>{_money(None if max_dd is None else int(max_dd), currency)}</td>"
                + f"<td>{_metric(row['avg_edge_pct'], suffix='%', signed=True)}</td>"
                + f"<td>{_metric(row['avg_ev_pct'], suffix='%', signed=True)}</td>"
                + f"<td>{escape(str(row['sample_band']))}</td>"
            )
        rendered.append("<tr>" + dimension_cells + metric_cells + "</tr>")
    if not rendered:
        metric_count = 11 if lab_key == "card" else 17
        rendered.append(
            f'<tr><td class="empty" colspan="{len(dimensions) + metric_count}">No settled picks for this breakdown.</td></tr>'
        )
    return (
        f'<section class="panel" id="{anchor}">'
        f'<div class="panel-title"><b>{escape(title)}</b><span>click group name for exact picks · click headers to sort</span></div>'
        '<div class="table"><table><thead><tr>'
        + headers
        + '</tr></thead><tbody>'
        + "".join(rendered)
        + "</tbody></table></div></section>"
    )



def _probability_bin_index(row: dict[str, Any]) -> int | None:
    if _result(row) not in {"WIN", "LOSS"} or row.get("model_probability") is None:
        return None
    probability = min(1.0, max(0.0, float(row["model_probability"])))
    return min(9, int(probability * 10))


def _bucket_detail_rows(
    rows: tuple[dict[str, Any], ...],
    params: dict[str, list[str]],
) -> tuple[tuple[dict[str, Any], ...], str] | None:
    if params.get("bucket", [""])[0] != "1":
        return None

    probability_bin = params.get("bucket_probability_bin", [""])[0].strip()
    if probability_bin:
        try:
            bucket_index = int(probability_bin)
        except ValueError:
            return ((), "Invalid probability bucket")
        if bucket_index < 0 or bucket_index > 9:
            return ((), "Invalid probability bucket")
        selected = tuple(
            row for row in rows
            if _probability_bin_index(row) == bucket_index
        )
        return (
            _sorted(selected),
            f"Model probability {bucket_index / 10:.1f}–{(bucket_index + 1) / 10:.1f}",
        )

    filters: dict[str, str] = {}
    for key, values in params.items():
        if (
            not key.startswith("bucket_")
            or key in {"bucket_probability_bin", "bucket_picks_sort", "bucket_picks_dir"}
            or not values
        ):
            continue
        raw = values[0]
        if raw:
            filters[key[len("bucket_"):]] = raw
    if not filters:
        return ((), "No bucket filters")

    selected = tuple(
        row
        for row in rows
        if _result(row) in {"WIN", "LOSS", "VOID"}
        and all(str(row.get(dimension) or "—") == value for dimension, value in filters.items())
    )
    label = " · ".join(
        f"{dimension.replace('_', ' ').title()}: {value}"
        for dimension, value in filters.items()
    )
    return _sorted(selected), label


def _pick_sort_value(row: dict[str, Any], key: str) -> Any:
    if key == "match":
        return (
            str(row.get("home_team") or "").casefold(),
            str(row.get("away_team") or "").casefold(),
        )
    if key == "pick":
        return _pick_text(row).casefold()
    if key == "result":
        return _result(row)
    if key == "settled_at":
        return _event_time(row).timestamp()
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return str(value).casefold()


def _sort_pick_rows(
    rows: tuple[dict[str, Any], ...],
    *,
    key: str,
    direction: str,
) -> tuple[dict[str, Any], ...]:
    present = [row for row in rows if _pick_sort_value(row, key) is not None]
    missing = [row for row in rows if _pick_sort_value(row, key) is None]
    present.sort(
        key=lambda row: _pick_sort_value(row, key),
        reverse=direction == "desc",
    )
    return tuple(present + missing)


def _bucket_pick_table(
    rows: tuple[dict[str, Any], ...],
    *,
    params: dict[str, list[str]],
    lab_key: str,
    currency: str,
) -> str:
    detail = _bucket_detail_rows(rows, params)
    if detail is None:
        return ""
    selected, label = detail
    allowed_sort_keys = {
        "match",
        "pick",
        "bookmaker_name",
        "model_probability",
        "odds",
        "edge",
        "expected_value",
        "result",
        "pnl_minor",
        "settled_at",
    }
    sort_key = _param(params, "bucket_picks_sort", "settled_at")
    if sort_key not in allowed_sort_keys:
        sort_key = "settled_at"
    sort_dir = _param(params, "bucket_picks_dir", "desc").casefold()
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    selected = _sort_pick_rows(selected, key=sort_key, direction=sort_dir)

    header_specs = (
        ("Match", "match", "asc"),
        ("Pick", "pick", "asc"),
        ("Bookmaker", "bookmaker_name", "asc"),
        ("Model P", "model_probability", "desc"),
        ("Odds", "odds", "desc"),
        ("Edge", "edge", "desc"),
        ("EV", "expected_value", "desc"),
        ("Result", "result", "asc"),
        ("P/L", "pnl_minor", "desc"),
        ("Settled", "settled_at", "desc"),
    )
    headers = "".join(
        _sortable_th(
            label_text,
            key,
            table_key="bucket_picks",
            params=params,
            anchor="bucket-picks",
            active_key=sort_key,
            active_dir=sort_dir,
            first_dir=first_dir,
        )
        for label_text, key, first_dir in header_specs
    )

    rendered = []
    for row in selected:
        result = _result(row)
        pnl_raw = row.get("pnl_minor")
        pnl = None if pnl_raw is None else int(pnl_raw)
        pnl_class = "positive" if (pnl or 0) > 0 else "negative" if (pnl or 0) < 0 else "neutral"
        rendered.append(
            "<tr>"
            + _match_html(row, lab_key=lab_key)
            + f'<td><b>{escape(_pick_text(row))}</b></td>'
            + f"<td>{_bookmaker(row.get('bookmaker_name'))}</td>"
            + f"<td>{_pct(row.get('model_probability'))}</td>"
            + f"<td>{_odd(row.get('odds'))}</td>"
            + f"<td>{_pct(row.get('edge'), signed=True)}</td>"
            + f"<td>{_pct(row.get('expected_value'), signed=True)}</td>"
            + f"<td>{_result_badge(result)}</td>"
            + f'<td class="{pnl_class}">{_money(pnl, currency)}</td>'
            + f"<td>{_time(row.get('settled_at'))}</td>"
            + "</tr>"
        )
    if not rendered:
        rendered.append(
            '<tr><td class="empty" colspan="10">No settled picks match this bucket.</td></tr>'
        )
    clear_href = _analytics_href(
        params,
        updates={"bucket": None},
        clear_prefixes=("bucket",),
    )
    return (
        '<section class="panel" id="bucket-picks">'
        '<div class="panel-title"><b>Bucket picks</b>'
        f'<span>{len(selected)} exact settled picks · {escape(label)} · '
        f'<a href="{escape(clear_href, quote=True)}">clear</a></span></div>'
        '<div class="table"><table><thead><tr>'
        + headers
        + '</tr></thead><tbody>'
        + "".join(rendered)
        + "</tbody></table></div></section>"
    )

def _window_rows(
    rows: tuple[dict[str, Any], ...],
    *,
    days: int,
    now: datetime,
) -> tuple[dict[str, Any], ...]:
    cutoff = now - timedelta(days=days)
    return tuple(
        row for row in rows
        if cutoff <= _event_time(row) <= now
    )


def _window_card(title: str, metrics: dict[str, Any]) -> str:
    return (
        '<section class="panel"><div class="panel-title"><b>'
        + escape(title)
        + '</b><span>settled performance</span></div><div class="metric-list">'
        + f'<div class="metric-line"><span>Settled</span><b>{metrics["n"]}</b></div>'
        + f'<div class="metric-line"><span>W-L-V</span><b>{metrics["wins"]}-{metrics["losses"]}-{metrics["voids"]}</b></div>'
        + f'<div class="metric-line"><span>Win rate</span><b>{_metric(metrics["win_rate_pct"], suffix="%")}</b></div>'
        + f'<div class="metric-line"><span>ROI</span><b>{_metric(metrics["roi_pct"], suffix="%", signed=True)}</b></div>'
        + f'<div class="metric-line"><span>Brier</span><b>{_metric(metrics["brier_score"], digits=3)}</b></div>'
        + f'<div class="metric-line"><span>Calibration</span><b>{_metric(metrics["calibration_gap_pp"], suffix="pp", signed=True)}</b></div>'
        + "</div></section>"
    )


def _calibration_sort_value(row: dict[str, Any], key: str) -> Any:
    if key == "bin":
        return float(str(row.get("bin") or "0").split("–", 1)[0])
    value = row.get(key)
    if value is None:
        return None
    return float(value) if isinstance(value, (int, float)) else str(value).casefold()


def _calibration_table(
    rows: tuple[dict[str, Any], ...],
    *,
    lab_key: str,
    params: dict[str, list[str]],
) -> str:
    bins = tuple(calibration_bins(rows))
    allowed = {"bin", "n", "expected_pct", "observed_pct", "gap_pp"}
    sort_key = _param(params, "calibration_sort", "bin")
    if sort_key not in allowed:
        sort_key = "bin"
    sort_dir = _param(params, "calibration_dir", "asc").casefold()
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "asc"
    present = [item for item in bins if _calibration_sort_value(item, sort_key) is not None]
    missing = [item for item in bins if _calibration_sort_value(item, sort_key) is None]
    present.sort(
        key=lambda item: _calibration_sort_value(item, sort_key),
        reverse=sort_dir == "desc",
    )
    bins = tuple(present + missing)
    anchor = "analytics-calibration"
    header_specs = (
        ("Probability bin", "bin", "asc"),
        ("N", "n", "desc"),
        ("Expected", "expected_pct", "desc"),
        ("Observed", "observed_pct", "desc"),
        ("Gap", "gap_pp", "desc"),
    )
    headers = "".join(
        _sortable_th(
            label,
            key,
            table_key="calibration",
            params=params,
            anchor=anchor,
            active_key=sort_key,
            active_dir=sort_dir,
            first_dir=first_dir,
        )
        for label, key, first_dir in header_specs
    )

    rendered_rows = []
    for item in bins:
        lower = float(str(item["bin"]).split("–", 1)[0])
        bucket_index = round(lower * 10)
        href = _analytics_href(
            params,
            updates={
                "bucket": "1",
                "bucket_probability_bin": str(bucket_index),
            },
            anchor="bucket-picks",
            clear_prefixes=("bucket",),
        )
        rendered_rows.append(
            "<tr>"
            f'<td><a class="group-link" href="{escape(href, quote=True)}">'
            f'{escape(str(item["bin"]))}</a></td>'
            f"<td>{item['n']}</td>"
            f"<td>{_metric(item['expected_pct'], suffix='%')}</td>"
            f"<td>{_metric(item['observed_pct'], suffix='%')}</td>"
            f"<td>{_metric(item['gap_pp'], suffix='pp', signed=True)}</td>"
            "</tr>"
        )
    rendered = "".join(rendered_rows)
    if not rendered:
        rendered = '<tr><td class="empty" colspan="5">No graded picks for calibration yet.</td></tr>'
    return (
        f'<section class="panel" id="{anchor}"><div class="panel-title"><b>Calibration</b>'
        '<span>click probability bin for exact picks · click headers to sort</span></div>'
        '<div class="table"><table><thead><tr>'
        + headers
        + f'</tr></thead><tbody>{rendered}</tbody></table></div></section>'
    )


def _goal_audit(
    repository: Any,
    rows: tuple[dict[str, Any], ...],
    *,
    params: dict[str, list[str]],
    lab_key: str,
) -> str:
    loader = getattr(repository, "list_all_goal_decision_evidence", None)
    if not callable(loader):
        loader = getattr(repository, "list_all_goal_decisions", None)
    try:
        decisions = tuple(loader()) if callable(loader) else ()
    except Exception:  # noqa: BLE001 - dashboard must degrade on repository read failures
        decisions = ()
    snapshot = build_goal_analytics_snapshot(rows, decisions)
    audit = snapshot["integrity_audit"]
    status = str(audit["status"])
    css = "audit-pass" if status == "PASS" else "audit-fail"

    items = tuple(snapshot["decision_funnel"])
    allowed = {"decision", "reason", "fixture_count", "rows"}
    sort_key = _param(params, "audit_sort", "rows")
    if sort_key not in allowed:
        sort_key = "rows"
    sort_dir = _param(params, "audit_dir", "desc").casefold()
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"

    def audit_value(item: dict[str, Any]) -> Any:
        value = item.get(sort_key)
        if value is None:
            return None
        return float(value) if isinstance(value, (int, float)) else str(value).casefold()

    present = [item for item in items if audit_value(item) is not None]
    missing = [item for item in items if audit_value(item) is None]
    present.sort(key=audit_value, reverse=sort_dir == "desc")
    items = tuple(present + missing)

    anchor = "analytics-audit"
    header_specs = (
        ("Decision", "decision", "asc"),
        ("Reason", "reason", "asc"),
        ("Fixtures", "fixture_count", "desc"),
        ("Rows", "rows", "desc"),
    )
    headers = "".join(
        _sortable_th(
            label,
            key,
            table_key="audit",
            params=params,
            anchor=anchor,
            active_key=sort_key,
            active_dir=sort_dir,
            first_dir=first_dir,
        )
        for label, key, first_dir in header_specs
    )
    funnel = "".join(
        "<tr>"
        f"<td><b>{escape(str(item['decision']))}</b></td>"
        f"<td>{escape(str(item['reason']))}</td>"
        f"<td>{item['fixture_count']}</td><td>{item['rows']}</td>"
        "</tr>"
        for item in items
    )
    if not funnel:
        funnel = '<tr><td class="empty" colspan="4">No decision evidence yet.</td></tr>'
    return (
        f'<section class="panel" id="{anchor}"><div class="panel-title"><b>GoalLab Research / Audit</b>'
        f'<span class="{css}">integrity {escape(status)} · {audit["violations"]} violations</span></div>'
        '<div class="table"><table><thead><tr>'
        + headers
        + f'</tr></thead><tbody>{funnel}</tbody></table></div></section>'
    )

def render_analytics(
    repository: Any,
    *,
    lab_key: str,
    currency: str,
    params: dict[str, list[str]] | None = None,
) -> str:
    lab, title, subtitle = LABS[lab_key]
    rows = _analytics_rows(
        _sorted(_all_rows(repository, lab)),
        lab_key=lab_key,
    )
    params = params or {}
    metrics = goal_pick_metrics(rows)
    now = datetime.now(UTC)
    last_7 = goal_pick_metrics(_window_rows(rows, days=7, now=now))
    last_30 = goal_pick_metrics(_window_rows(rows, days=30, now=now))

    top_cards = (
        (
            ("Settled", str(metrics["n"])),
            ("Unique matches", str(len({str(row.get("fixture_id") or "") for row in rows if _result(row) in {"WIN", "LOSS", "VOID"}}))),
            ("W-L-V", f'{metrics["wins"]}-{metrics["losses"]}-{metrics["voids"]}'),
            ("Win rate", _metric(metrics["win_rate_pct"], suffix="%")),
            ("ROI", _metric(metrics["roi_pct"], suffix="%", signed=True)),
            ("P/L", _money(int(metrics["pnl_minor"]), currency)),
            ("Avg odds", _metric(metrics["avg_odds"], digits=2)),
            ("Max DD", _money(int(metrics["max_drawdown_minor"]), currency)),
        )
        if lab_key == "card"
        else (
            ("Settled", str(metrics["n"])),
            ("W-L-V", f'{metrics["wins"]}-{metrics["losses"]}-{metrics["voids"]}'),
            ("Win rate", _metric(metrics["win_rate_pct"], suffix="%")),
            ("Expected", _metric(metrics["expected_win_rate_pct"], suffix="%")),
            ("Calibration", _metric(metrics["calibration_gap_pp"], suffix="pp", signed=True)),
            ("ROI", _metric(metrics["roi_pct"], suffix="%", signed=True)),
            ("P/L", _money(int(metrics["pnl_minor"]), currency)),
            ("Avg odds", _metric(metrics["avg_odds"], digits=2)),
            ("Brier", _metric(metrics["brier_score"], digits=3)),
            ("Log loss", _metric(metrics["log_loss"], digits=3)),
            ("Avg CLV", _metric(metrics["avg_clv_pct"], suffix="%", signed=True)),
            ("CLV coverage", _metric(metrics["closing_coverage_pct"], suffix="%")),
            ("Max DD", _money(int(metrics["max_drawdown_minor"]), currency)),
            ("Avg edge", _metric(metrics["avg_edge_pct"], suffix="%", signed=True)),
            ("Avg EV", _metric(metrics["avg_ev_pct"], suffix="%", signed=True)),
        )
    )
    cards_html = "".join(
        f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
        for label, value in top_cards
    )

    analytics_note = (
        "GoalLab analytics now uses Research-style stable buckets, cross-sections, timing cohorts, "
        "version regimes, calibration and exact constituent-pick drilldowns."
        if lab_key == "goal"
        else "CornerLab analytics now uses Research-style stable buckets, cross-sections, timing cohorts, "
        "version regimes, calibration and exact constituent-pick drilldowns."
        if lab_key == "corner"
        else "CardLab is raw-statistics first: PICK decisions do not require EV, edge or an odds band. "
        "Analytics exposes referee, team discipline, foul, matchup, league, H2H, importance, game-state, "
        "trend and reliability buckets with exact constituent-pick drilldowns."
    )

    def table(
        title_text: str,
        dimensions: tuple[str, ...],
        table_key: str,
        *,
        labels: dict[str, str] | None = None,
        drop_missing: bool = False,
        min_groups: int = 1,
    ) -> str:
        eligible_rows = rows
        if drop_missing:
            eligible_rows = tuple(
                row
                for row in rows
                if all(
                    str(row.get(dimension) or "—") != "—"
                    for dimension in dimensions
                )
            )
        if not _dimension_available(eligible_rows, dimensions):
            return ""
        cohorts = _cohorts(eligible_rows, dimensions)
        if len(cohorts) < min_groups:
            return ""
        return _cohort_table(
            title_text,
            cohorts,
            dimensions,
            lab_key=lab_key,
            table_key=table_key,
            params=params,
            currency=currency,
            dimension_labels=labels,
        )

    if lab_key == "goal":
        watchlist_content = (
            table(
                "Goal shape × price",
                (
                    "market_key",
                    "selection",
                    "expected_total_goals_bucket",
                    "goal_lambda_min_bucket",
                    "entry_odds_bucket",
                ),
                "watch_goal_shape_price",
                labels={
                    "market_key": "Market",
                    "selection": "Selection",
                    "expected_total_goals_bucket": "λ total",
                    "goal_lambda_min_bucket": "λ min",
                    "entry_odds_bucket": "Odds",
                },
                drop_missing=True,
            )
            + table(
                "Balance × total-line gap",
                (
                    "market_key",
                    "selection",
                    "goal_lambda_balance_bucket",
                    "goal_total_line_gap_bucket",
                ),
                "watch_goal_balance_gap",
                labels={
                    "market_key": "Market",
                    "selection": "Selection",
                    "goal_lambda_balance_bucket": "λ balance",
                    "goal_total_line_gap_bucket": "λ total − line",
                },
                drop_missing=True,
            )
            + table(
                "Model vs market × price",
                (
                    "market_key",
                    "selection",
                    "model_probability_bucket",
                    "market_probability_bucket",
                    "entry_odds_bucket",
                ),
                "watch_goal_price",
                labels={
                    "market_key": "Market",
                    "selection": "Selection",
                    "model_probability_bucket": "Model P",
                    "market_probability_bucket": "Market P",
                    "entry_odds_bucket": "Odds",
                },
                drop_missing=True,
            )
            + table(
                "Trend × matchup",
                (
                    "market_key",
                    "selection",
                    "goal_attack_trend_bucket",
                    "goal_venue_trend_bucket",
                    "goal_matchup_pressure_bucket",
                ),
                "watch_goal_trend_matchup",
                labels={
                    "market_key": "Market",
                    "selection": "Selection",
                    "goal_attack_trend_bucket": "L5−L10 goals",
                    "goal_venue_trend_bucket": "Venue−L10",
                    "goal_matchup_pressure_bucket": "Matchup pressure",
                },
                drop_missing=True,
            )
            + table(
                "Reliability × market",
                (
                    "market_key",
                    "selection",
                    "history_depth_bucket",
                    "feature_missingness_bucket",
                ),
                "watch_goal_reliability",
                labels={
                    "market_key": "Market",
                    "selection": "Selection",
                    "history_depth_bucket": "Min history",
                    "feature_missingness_bucket": "Missing features",
                },
                drop_missing=True,
            )
        )
    elif lab_key == "corner":
        watchlist_content = (
            table(
                "Calibration watch · line × price",
                (
                    "corner_calibration_watch_bucket",
                    "selection",
                    "line_bucket",
                    "model_probability_bucket",
                    "market_probability_bucket",
                    "entry_odds_bucket",
                ),
                "watch_corner_calibration",
                labels={
                    "corner_calibration_watch_bucket": "Watch regime",
                    "selection": "Selection",
                    "line_bucket": "Line",
                    "model_probability_bucket": "Model P",
                    "market_probability_bucket": "Market P",
                    "entry_odds_bucket": "Odds",
                },
                drop_missing=True,
            )
            + table(
                "Model-line gap × price",
                (
                    "market_key",
                    "selection",
                    "corner_model_line_gap_bucket",
                    "entry_odds_bucket",
                ),
                "watch_corner_gap_price",
                labels={
                    "market_key": "Market",
                    "selection": "Selection",
                    "corner_model_line_gap_bucket": "Mean − line",
                    "entry_odds_bucket": "Odds",
                },
                drop_missing=True,
            )
            + table(
                "Pressure trend × matchup",
                (
                    "selection",
                    "corner_trend_bucket",
                    "corner_venue_trend_bucket",
                    "corner_matchup_pressure_bucket",
                ),
                "watch_corner_trend_matchup",
                labels={
                    "selection": "Selection",
                    "corner_trend_bucket": "L5−L10 corners",
                    "corner_venue_trend_bucket": "Venue−L10",
                    "corner_matchup_pressure_bucket": "Matchup pressure",
                },
                drop_missing=True,
            )
            + table(
                "Model vs market × price",
                (
                    "market_key",
                    "selection",
                    "model_probability_bucket",
                    "market_probability_bucket",
                    "entry_odds_bucket",
                ),
                "watch_corner_price",
                labels={
                    "market_key": "Market",
                    "selection": "Selection",
                    "model_probability_bucket": "Model P",
                    "market_probability_bucket": "Market P",
                    "entry_odds_bucket": "Odds",
                },
                drop_missing=True,
            )
            + table(
                "Reliability × market",
                (
                    "market_key",
                    "selection",
                    "history_depth_bucket",
                    "feature_missingness_bucket",
                ),
                "watch_corner_reliability",
                labels={
                    "market_key": "Market",
                    "selection": "Selection",
                    "history_depth_bucket": "Min history",
                    "feature_missingness_bucket": "Missing features",
                },
                drop_missing=True,
            )
        )

    else:
        watchlist_content = (
            table(
                "RAW consensus × line × support",
                (
                    "selection",
                    "line_bucket",
                    "card_raw_consensus_bucket",
                    "card_raw_line_gap_bucket",
                    "card_raw_support_bucket",
                    "card_raw_hit_rate_bucket",
                ),
                "watch_card_raw_signal",
                labels={
                    "selection": "Pick",
                    "line_bucket": "Line",
                    "card_raw_consensus_bucket": "Raw total",
                    "card_raw_line_gap_bucket": "Raw − line",
                    "card_raw_support_bucket": "Anchor support",
                    "card_raw_hit_rate_bucket": "Observed hit",
                },
                drop_missing=True,
            )
            + table(
                "Referee × team discipline × price",
                (
                    "selection",
                    "card_referee_cards_l10_bucket",
                    "card_combined_cards_l10_bucket",
                    "entry_odds_bucket",
                ),
                "watch_card_ref_team",
                labels={
                    "selection": "Pick",
                    "card_referee_cards_l10_bucket": "Ref L10 cards",
                    "card_combined_cards_l10_bucket": "Teams L10 cards",
                    "entry_odds_bucket": "Odds",
                },
                drop_missing=True,
            )
            + table(
                "Referee × fouls × matchup",
                (
                    "selection",
                    "card_referee_fouls_l10_bucket",
                    "card_combined_fouls_l10_bucket",
                    "card_matchup_fouls_bucket",
                ),
                "watch_card_fouls",
                labels={
                    "selection": "Pick",
                    "card_referee_fouls_l10_bucket": "Ref fouls",
                    "card_combined_fouls_l10_bucket": "Team fouls",
                    "card_matchup_fouls_bucket": "Matchup fouls",
                },
                drop_missing=True,
            )
            + table(
                "Discipline × foul-drawing interaction",
                (
                    "selection",
                    "card_home_cards_per_foul_bucket",
                    "card_away_cards_per_foul_bucket",
                    "card_aggression_foul_draw_bucket",
                ),
                "watch_card_discipline_draw",
                labels={
                    "selection": "Pick",
                    "card_home_cards_per_foul_bucket": "Home cards/foul",
                    "card_away_cards_per_foul_bucket": "Away cards/foul",
                    "card_aggression_foul_draw_bucket": "Aggression × draw",
                },
                drop_missing=True,
            )
            + table(
                "Importance × derby/cup × competitiveness",
                (
                    "selection",
                    "card_importance_bucket",
                    "card_derby_bucket",
                    "card_cup_bucket",
                    "card_similar_strength_bucket",
                ),
                "watch_card_context",
                labels={
                    "selection": "Pick",
                    "card_importance_bucket": "Importance",
                    "card_derby_bucket": "Derby",
                    "card_cup_bucket": "Competition",
                    "card_similar_strength_bucket": "Strength",
                },
                drop_missing=True,
            )
            + table(
                "Trend × venue × referee delta",
                (
                    "selection",
                    "card_cards_trend_bucket",
                    "card_venue_cards_trend_bucket",
                    "card_referee_vs_teams_bucket",
                ),
                "watch_card_trend",
                labels={
                    "selection": "Pick",
                    "card_cards_trend_bucket": "L5−L10 cards",
                    "card_venue_cards_trend_bucket": "Venue−L10",
                    "card_referee_vs_teams_bucket": "Ref − teams",
                },
                drop_missing=True,
            )
            + table(
                "Reliability × unique-match exposure",
                (
                    "selection",
                    "history_depth_bucket",
                    "feature_missingness_bucket",
                    "card_raw_anchor_count_bucket",
                    "card_fixture_pick_count_bucket",
                ),
                "watch_card_reliability",
                labels={
                    "selection": "Pick",
                    "history_depth_bucket": "Min team history",
                    "feature_missingness_bucket": "Missing",
                    "card_raw_anchor_count_bucket": "Anchors",
                    "card_fixture_pick_count_bucket": "Picks/match",
                },
                drop_missing=True,
            )
        )

    watchlist = _watchlist_block(watchlist_content, lab_key=lab_key)

    baseline = (
        _analytics_section(
            "Universe / regimes",
            "core categorical cohorts only",
        )
        + table(
            "Markets / selections",
            ("market_key", "selection"),
            "markets",
            labels={"market_key": "Market", "selection": "Selection"},
        )
        + table(
            "Leagues",
            ("competition_name",),
            "leagues",
            labels={"competition_name": "League"},
        )
        + table(
            "Bookmakers",
            ("bookmaker_name",),
            "bookmakers",
            labels={"bookmaker_name": "Bookmaker"},
        )
        + table(
            "Model versions",
            ("model_version",),
            "models",
            labels={"model_version": "Model version"},
            min_groups=2,
        )
        + table(
            "Policy versions",
            ("policy_version",),
            "policies",
            labels={"policy_version": "Policy version"},
            min_groups=2,
        )
        + table(
            "Model × policy",
            ("model_version", "policy_version"),
            "model_policy",
            labels={
                "model_version": "Model version",
                "policy_version": "Policy version",
            },
            min_groups=2,
        )
    )

    signal_buckets = (
        _analytics_section(
            "Signal / price",
            "compact price diagnostics; watchlist contains the important crosses",
        )
        + table(
            "Entry odds",
            ("entry_odds_bucket",),
            "entry_odds",
            labels={"entry_odds_bucket": "Entry odds"},
            drop_missing=True,
        )
        + table(
            "Edge",
            ("edge_bucket",),
            "edge",
            labels={"edge_bucket": "Edge"},
            drop_missing=True,
        )
        + table(
            "Expected value",
            ("ev_bucket",),
            "ev",
            labels={"ev_bucket": "EV"},
            drop_missing=True,
        )
        + table(
            "Realized CLV",
            ("clv_bucket",),
            "clv",
            labels={"clv_bucket": "CLV"},
            drop_missing=True,
        )
    )

    timing = (
        _analytics_section(
            "Stability",
            "time slices useful for validation, not primary selection",
        )
        + table(
            "Weekly stability",
            ("kickoff_week",),
            "weeks",
            labels={"kickoff_week": "Week"},
            drop_missing=True,
        )
        + table(
            "Decision lead time",
            ("decision_lead_bucket",),
            "decision_lead",
            labels={"decision_lead_bucket": "Kickoff − decision"},
            drop_missing=True,
        )
    )

    cross_sections = (
        _analytics_section(
            "Execution cross-sections",
            "secondary checks for league and bookmaker concentration",
        )
        + table(
            "League × market",
            ("competition_name", "market_key", "selection"),
            "league_market",
            labels={
                "competition_name": "League",
                "market_key": "Market",
                "selection": "Selection",
            },
        )
        + table(
            "Bookmaker × market",
            ("bookmaker_name", "market_key", "selection"),
            "bookmaker_market",
            labels={
                "bookmaker_name": "Bookmaker",
                "market_key": "Market",
                "selection": "Selection",
            },
        )
    )

    if lab_key == "goal":
        domain = (
            _analytics_section(
                "GoalLab structure",
                "secondary structural summaries; ROI candidates are promoted to Watchlist",
            )
            + table(
                "Expected total goals",
                ("expected_total_goals_bucket",),
                "goal_total",
                labels={"expected_total_goals_bucket": "λ total"},
                drop_missing=True,
            )
            + table(
                "Home − away expected-goal spread",
                ("goal_lambda_spread_bucket",),
                "goal_spread",
                labels={"goal_lambda_spread_bucket": "λH − λA"},
                drop_missing=True,
            )
        )
    else:
        domain = (
            _analytics_section(
                "CornerLab structure",
                "secondary model-state summary; gap × price is promoted to Watchlist",
            )
            + table(
                "Expected total corners",
                ("expected_total_corners_bucket",),
                "corner_total",
                labels={"expected_total_corners_bucket": "Expected corners"},
                drop_missing=True,
            )
        )

    body = (
        f'<p class="analytics-note">{escape(analytics_note)}</p>'
        f'<section class="cards">{cards_html}</section>'
        + _bucket_pick_table(
            rows,
            params=params,
            lab_key=lab_key,
            currency=currency,
        )
        + watchlist
        + '<div class="analytics-grid">'
        + _window_card("Last 7 days", last_7)
        + _window_card("Last 30 days", last_30)
        + _window_card("Lifetime", metrics)
        + "</div>"
        + baseline
        + signal_buckets
        + domain
        + timing
        + cross_sections
        + _analytics_section(
            "Calibration",
            "probability reliability and exact graded constituents",
        )
        + _calibration_table(rows, lab_key=lab_key, params=params)
        + (
            _analytics_section(
                "GoalLab decision audit",
                "decision evidence and integrity checks",
            )
            + _goal_audit(
                repository,
                rows,
                params=params,
                lab_key=lab_key,
            )
            if lab_key == "goal"
            else ""
        )
    )

    return _shell(
        title=f"{title} Analytics",
        subtitle=subtitle,
        view="analytics",
        lab_key=lab_key,
        body=body,
    )



def render_quantlab_view(
    repository: Any,
    raw_query: str,
    *,
    api_daily_limit: int,
    currency: str,
) -> str:
    params = parse_qs(raw_query, keep_blank_values=True)
    view = params.get("view", ["dashboard"])[0].strip().casefold()
    if view not in {"dashboard", "analytics"}:
        view = "dashboard"

    lab_key = params.get("lab", ["goal"])[0].strip().casefold()
    if lab_key not in LABS:
        lab_key = "goal"
    if view == "analytics" and lab_key not in ANALYTICS_LABS:
        lab_key = "goal"

    if view == "analytics":
        return render_analytics(
            repository,
            lab_key=lab_key,
            currency=currency,
            params=params,
        )
    return render_dashboard(
        repository,
        lab_key=lab_key,
        api_daily_limit=api_daily_limit,
        currency=currency,
    )
