"""Simplified operational and analytics views for QuantLab.

This module is presentation-only. It reads the existing QuantLab ledgers and does not
write to production, alter model authority, or change collector/modeler/settlement logic.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

from h2h.quantlab.goal_analytics import (
    build_goal_analytics_snapshot,
    calibration_bins,
    goal_pick_metrics,
)

BELGRADE = ZoneInfo("Europe/Belgrade")

LABS = {
    "goal": ("GOAL", "GoalLab", "Goals · DC+ and goal-market experiments"),
    "corner": ("CORNER", "CornerLab", "Corners · totals, team totals and handicaps"),
    "card": ("CARD", "CardLab", "Cards · totals, team cards and referee-sensitive models"),
}
ANALYTICS_LABS = {"goal", "corner"}


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


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
td.match{{min-width:250px}}small{{display:block;color:var(--muted);font-size:10px;margin-top:4px}}
.badge{{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:9px;font-weight:950}}
.result-win{{color:#82dda6;background:rgba(105,201,143,.14)}}.result-loss{{color:#f08790;background:rgba(224,111,120,.14)}}
.result-void{{color:#b6bdc3;background:rgba(154,161,168,.12)}}.result-pending{{color:#d7b36f;background:rgba(198,163,93,.12)}}
.positive{{color:var(--win)}}.negative{{color:var(--loss)}}.neutral{{color:var(--text)}}
.bookmaker{{display:inline-flex;align-items:center;justify-content:center;min-width:78px;height:27px;padding:0 8px;border-radius:7px;font-weight:900;background:#232a30}}
.bookmaker-bet365{{background:#146947}}.bookmaker-bet365 strong{{color:#f3d24b}}.bookmaker-1xbet{{background:#182f47}}.bookmaker-1xbet strong{{color:#61aef4}}
.empty{{text-align:center;padding:34px!important;color:var(--muted)}}
.analytics-note{{margin:0 0 14px;padding:11px 13px;border-left:3px solid var(--warn);background:#171b1f;color:#aab2b9;font-size:12px}}
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
</main></body></html>"""


def _active_rows_html(rows: tuple[dict[str, Any], ...], *, lab_key: str) -> str:
    rendered = []
    for row in rows:
        rendered.append(
            "<tr>"
            + _match_html(row, lab_key=lab_key)
            + f'<td><b>{escape(_pick_text(row))}</b></td>'
            + f"<td>{_bookmaker(row.get('bookmaker_name'))}</td>"
            + f"<td>{_pct(row.get('model_probability'))}<small>market {_pct(row.get('market_probability'))}</small></td>"
            + f"<td>{_odd(row.get('odds'))}</td>"
            + f"<td>{_pct(row.get('edge'), signed=True)}</td>"
            + f"<td>{_pct(row.get('expected_value'), signed=True)}</td>"
            + f"<td>{_result_badge('PENDING')}</td>"
            + f"<td>{_time(row.get('decision_at'))}</td>"
            + "</tr>"
        )
    if not rendered:
        return '<tr><td class="empty" colspan="9">No active picks.</td></tr>'
    return "".join(rendered)


def _history_rows_html(
    rows: tuple[dict[str, Any], ...],
    *,
    lab_key: str,
    currency: str,
) -> str:
    rendered = []
    for row in rows:
        result = _result(row)
        pnl_raw = row.get("pnl_minor")
        pnl = None if pnl_raw is None else int(pnl_raw)
        pnl_class = "positive" if (pnl or 0) > 0 else "negative" if (pnl or 0) < 0 else "neutral"
        rendered.append(
            "<tr>"
            + _match_html(row, lab_key=lab_key)
            + f'<td><b>{escape(_pick_text(row))}</b></td>'
            + f"<td>{_bookmaker(row.get('bookmaker_name'))}</td>"
            + f"<td>{_odd(row.get('odds'))}</td>"
            + f"<td>{_result_badge(result)}</td>"
            + f'<td class="{pnl_class}">{_money(pnl, currency)}</td>'
            + f"<td>{_time(row.get('settled_at'))}</td>"
            + "</tr>"
        )
    if not rendered:
        return '<tr><td class="empty" colspan="7">No settled picks yet.</td></tr>'
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
    except Exception:
        rows = ()
        warning = (
            '<p class="analytics-note">Pick ledger temporarily unavailable. '
            'QuantLab processing is unchanged; this is a read-only dashboard error.</p>'
        )

    if lab == "GOAL":
        loader = getattr(repository, "list_all_goal_picks", None)
        metric_rows = _sorted(tuple(loader())) if callable(loader) else rows
    else:
        loader = getattr(repository, "list_all_bets", None)
        metric_rows = _sorted(tuple(loader(lab))) if callable(loader) else rows

    active = tuple(row for row in rows if _result(row) == "PENDING")
    history = tuple(row for row in rows if _result(row) in {"WIN", "LOSS", "VOID"})
    metric_active = tuple(row for row in metric_rows if _result(row) == "PENDING")
    metric_history = tuple(
        row for row in metric_rows if _result(row) in {"WIN", "LOSS", "VOID"}
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
    except Exception:
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
        '<th>Odds</th><th>Edge</th><th>EV</th><th>Status</th><th>Decision</th>'
        f'</tr></thead><tbody>{_active_rows_html(active, lab_key=lab_key)}</tbody></table></div>'
        '</section>'
        '<section class="panel">'
        '<div class="panel-title"><b>Pick History</b>'
        f'<span>{len(history)} settled · WIN / LOSS / VOID</span></div>'
        '<div class="table"><table><thead><tr>'
        '<th>Match</th><th>Pick</th><th>Bookmaker</th><th>Odds</th>'
        '<th>Result</th><th>P/L</th><th>Settled</th>'
        f'</tr></thead><tbody>{_history_rows_html(history, lab_key=lab_key, currency=currency)}</tbody></table></div>'
        '</section>'
    )
    return _shell(
        title=title,
        subtitle=subtitle,
        view="dashboard",
        lab_key=lab_key,
        body=body,
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


def _cohort_table(
    title: str,
    rows: tuple[dict[str, Any], ...],
    dimensions: tuple[str, ...],
) -> str:
    headers = "".join(
        f"<th>{escape(dimension.replace('_', ' ').title())}</th>"
        for dimension in dimensions
    )
    rendered = []
    for row in rows:
        dimension_cells = "".join(
            f"<td><b>{escape(str(row.get(dimension) or '—'))}</b></td>"
            for dimension in dimensions
        )
        rendered.append(
            "<tr>"
            + dimension_cells
            + f"<td>{row['graded_n']}</td>"
            + f"<td>{row['wins']}-{row['losses']}-{row['voids']}</td>"
            + f"<td>{_metric(row['win_rate_pct'], suffix='%')}</td>"
            + f"<td>{_metric(row['roi_pct'], suffix='%', signed=True)}</td>"
            + f"<td>{_metric(row['brier_score'], digits=3)}</td>"
            + f"<td>{_metric(row['log_loss'], digits=3)}</td>"
            + f"<td>{_metric(row['calibration_gap_pp'], suffix='pp', signed=True)}</td>"
            + f"<td>{_metric(row['avg_edge_pct'], suffix='%', signed=True)}</td>"
            + f"<td>{_metric(row['avg_ev_pct'], suffix='%', signed=True)}</td>"
            + f"<td>{escape(str(row['sample_band']))}</td>"
            + "</tr>"
        )
    if not rendered:
        rendered.append(
            f'<tr><td class="empty" colspan="{len(dimensions) + 10}">No settled picks for this breakdown.</td></tr>'
        )
    return (
        '<section class="panel">'
        f'<div class="panel-title"><b>{escape(title)}</b><span>performance breakdown</span></div>'
        '<div class="table"><table><thead><tr>'
        + headers
        + '<th>N</th><th>W-L-V</th><th>Win%</th><th>ROI</th><th>Brier</th>'
        '<th>Log loss</th><th>Cal gap</th><th>Avg edge</th><th>Avg EV</th><th>Evidence</th>'
        '</tr></thead><tbody>'
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


def _calibration_table(rows: tuple[dict[str, Any], ...]) -> str:
    bins = calibration_bins(rows)
    rendered = "".join(
        "<tr>"
        f"<td><b>{escape(str(item['bin']))}</b></td>"
        f"<td>{item['n']}</td>"
        f"<td>{_metric(item['expected_pct'], suffix='%')}</td>"
        f"<td>{_metric(item['observed_pct'], suffix='%')}</td>"
        f"<td>{_metric(item['gap_pp'], suffix='pp', signed=True)}</td>"
        "</tr>"
        for item in bins
    )
    if not rendered:
        rendered = '<tr><td class="empty" colspan="5">No graded picks for calibration yet.</td></tr>'
    return (
        '<section class="panel"><div class="panel-title"><b>Calibration</b>'
        '<span>model probability vs observed result</span></div>'
        '<div class="table"><table><thead><tr>'
        '<th>Probability bin</th><th>N</th><th>Expected</th><th>Observed</th><th>Gap</th>'
        f'</tr></thead><tbody>{rendered}</tbody></table></div></section>'
    )


def _goal_audit(repository: Any, rows: tuple[dict[str, Any], ...]) -> str:
    loader = getattr(repository, "list_all_goal_decision_evidence", None)
    if not callable(loader):
        loader = getattr(repository, "list_all_goal_decisions", None)
    decisions = tuple(loader()) if callable(loader) else ()
    snapshot = build_goal_analytics_snapshot(rows, decisions)
    audit = snapshot["integrity_audit"]
    status = str(audit["status"])
    css = "audit-pass" if status == "PASS" else "audit-fail"
    funnel = "".join(
        "<tr>"
        f"<td><b>{escape(str(item['decision']))}</b></td>"
        f"<td>{escape(str(item['reason']))}</td>"
        f"<td>{item['fixture_count']}</td><td>{item['rows']}</td>"
        "</tr>"
        for item in snapshot["decision_funnel"]
    )
    if not funnel:
        funnel = '<tr><td class="empty" colspan="4">No decision evidence yet.</td></tr>'
    return (
        '<section class="panel"><div class="panel-title"><b>GoalLab Research / Audit</b>'
        f'<span class="{css}">integrity {escape(status)} · {audit["violations"]} violations</span></div>'
        '<div class="table"><table><thead><tr>'
        '<th>Decision</th><th>Reason</th><th>Fixtures</th><th>Rows</th>'
        f'</tr></thead><tbody>{funnel}</tbody></table></div></section>'
    )


def render_analytics(
    repository: Any,
    *,
    lab_key: str,
    currency: str,
) -> str:
    lab, title, subtitle = LABS[lab_key]
    rows = _sorted(_all_rows(repository, lab))
    metrics = goal_pick_metrics(rows)
    now = datetime.now(UTC)
    last_7 = goal_pick_metrics(_window_rows(rows, days=7, now=now))
    last_30 = goal_pick_metrics(_window_rows(rows, days=30, now=now))

    top_cards = (
        ("Settled", str(metrics["n"])),
        ("W-L-V", f'{metrics["wins"]}-{metrics["losses"]}-{metrics["voids"]}'),
        ("Win rate", _metric(metrics["win_rate_pct"], suffix="%")),
        ("ROI", _metric(metrics["roi_pct"], suffix="%", signed=True)),
        ("Brier", _metric(metrics["brier_score"], digits=3)),
        ("Log loss", _metric(metrics["log_loss"], digits=3)),
        ("Calibration", _metric(metrics["calibration_gap_pp"], suffix="pp", signed=True)),
        ("Max DD", _money(int(metrics["max_drawdown_minor"]), currency)),
    )
    cards_html = "".join(
        f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
        for label, value in top_cards
    )

    analytics_note = (
        "GoalLab analytics is isolated from the operational dashboard. It includes pick performance, "
        "calibration, cohort breakdowns and the existing decision audit."
        if lab_key == "goal"
        else
        "CornerLab analytics is isolated from the operational dashboard. It measures the settled pick "
        "ledger by market, league, bookmaker and model regime."
    )

    body = (
        f'<p class="analytics-note">{escape(analytics_note)}</p>'
        f'<section class="cards">{cards_html}</section>'
        '<div class="analytics-grid">'
        + _window_card("Last 7 days", last_7)
        + _window_card("Last 30 days", last_30)
        + _window_card("Lifetime", metrics)
        + "</div>"
        + _cohort_table(
            "Markets / selections",
            _cohorts(rows, ("market_key", "selection")),
            ("market_key", "selection"),
        )
        + _cohort_table(
            "Leagues",
            _cohorts(rows, ("competition_name",)),
            ("competition_name",),
        )
        + _cohort_table(
            "Bookmakers",
            _cohorts(rows, ("bookmaker_name",)),
            ("bookmaker_name",),
        )
        + _cohort_table(
            "Model versions",
            _cohorts(rows, ("model_version",)),
            ("model_version",),
        )
        + _calibration_table(rows)
        + (_goal_audit(repository, rows) if lab_key == "goal" else "")
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
        return render_analytics(repository, lab_key=lab_key, currency=currency)
    return render_dashboard(
        repository,
        lab_key=lab_key,
        api_daily_limit=api_daily_limit,
        currency=currency,
    )
