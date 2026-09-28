"""Read-only dashboard for QuantLab multi-market experiments."""

from __future__ import annotations

import base64
import hmac
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from h2h.domain.settlement import realized_clv_ppm
from h2h.quantlab.goal_analytics import (
    build_goal_analytics_snapshot,
    render_goal_analytics_html,
    render_goal_model_html,
    render_goal_pick_html,
)
from h2h.quantlab.goal_lab.explanations import render_goal_pick_note_html
from h2h.quantlab.goal_lab.picks import PICK_POLICY_VERSION
from h2h.quantlab.repository import PostgreSQLQuantLabRepository
from h2h.quantlab.scope import goal_scope


LOGGER = logging.getLogger("quantbet.quantlab.dashboard")
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


def _metric_text(
    value: Any,
    *,
    suffix: str = "",
    digits: int = 2,
    signed: bool = False,
) -> str:
    if value is None:
        return "—"
    number = float(value)
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.{digits}f}{suffix}"


def _corner_pick_note(row: dict[str, Any]) -> str:
    expected = _number(row.get("expected_total_corners"))
    line = _number(row.get("line"))
    model_p = _number(row.get("model_probability"))
    market_p = _number(row.get("market_probability"))
    edge = _number(row.get("edge"))
    ev = _number(row.get("expected_value"))
    selection = str(row.get("selection") or "—")

    payload = row.get("corner_feature_payload")
    raw = payload.get("raw_features") if isinstance(payload, dict) else {}
    raw = raw if isinstance(raw, dict) else {}

    def value(name: str) -> str:
        return _rate(raw.get(name))

    summary = (
        f"Model očekuje {_rate(expected)} ukupnih kornera. "
        f"{selection} {_rate(line)} ima modelsku verovatnoću {_pct(model_p)} "
        f"naspram tržišne {_pct(market_p)}; edge {_pct(edge)}, EV {_pct(ev)}."
    )
    form = (
        "L5 korneri za/protiv — "
        f"domaćin {value('home_l5_corners_for')}/{value('home_l5_corners_against')}, "
        f"gost {value('away_l5_corners_for')}/{value('away_l5_corners_against')}. "
        "L5 šutevi — "
        f"domaćin {value('home_l5_shots_for')} ({value('home_l5_sot_for')} u okvir), "
        f"gost {value('away_l5_shots_for')} ({value('away_l5_sot_for')} u okvir)."
    )
    return (
        '<details class="pick-note"><summary title="Zašto je sistem izabrao ovaj pik">📝</summary>'
        f'<div class="note-popover"><b>Zašto ovaj pik</b><span>{escape(summary)}</span>'
        f'<span>{escape(form)}</span></div></details>'
    )


def _drawdown(rows: tuple[dict[str, Any], ...]) -> int:
    chronological = sorted(
        (row for row in rows if row.get("pnl_minor") is not None),
        key=lambda row: (
            row.get("settled_at") or row["decision_at"],
            row.get("goal_pick_id") or row.get("shadow_bet_id") or row["fixture_id"],
        ),
    )
    equity = peak = 0
    max_drawdown = 0
    for row in chronological:
        equity += int(row["pnl_minor"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def _sort_value(value: Any) -> tuple[int, Any]:
    if value is None:
        return (1, "")
    if isinstance(value, datetime):
        return (0, value.timestamp())
    if isinstance(value, (int, float, Decimal)):
        return (0, float(value))
    return (0, str(value).casefold())


def _sort_rows(
    rows: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    key: str,
    direction: str,
) -> tuple[dict[str, Any], ...]:
    reverse = direction == "desc"
    present = [row for row in rows if row.get(key) is not None]
    missing = [row for row in rows if row.get(key) is None]
    present.sort(
        key=lambda row: (
            _sort_value(row.get(key))[1],
            str(row.get("goal_pick_id") or row.get("fixture_id") or ""),
        ),
        reverse=reverse,
    )
    return tuple(present + missing)


def _sortable_th(
    label: str,
    key: str,
    *,
    base_params: dict[str, str],
    sort_param: str,
    dir_param: str,
    active_key: str,
    active_dir: str,
    anchor: str,
) -> str:
    def href(direction: str) -> str:
        params = {name: value for name, value in base_params.items() if value != ""}
        params[sort_param] = key
        params[dir_param] = direction
        return "/quantlab?" + urlencode(params) + f"#{anchor}"

    return (
        '<th><span class="th-wrap"><span>'
        + escape(label)
        + '</span><span class="sort-tools">'
        + f'<a class="{"sort-active" if active_key == key and active_dir == "asc" else ""}" '
        + f'href="{escape(href("asc"), quote=True)}" title="Lowest first">↑</a>'
        + f'<a class="{"sort-active" if active_key == key and active_dir == "desc" else ""}" '
        + f'href="{escape(href("desc"), quote=True)}" title="Highest first">↓</a>'
        + "</span></span></th>"
    )


class QuantLabDashboardService:
    def __init__(
        self,
        repository: PostgreSQLQuantLabRepository,
        *,
        api_daily_limit: int = 75_000,
        currency: str = "RSD",
    ) -> None:
        if api_daily_limit <= 0:
            raise ValueError("api_daily_limit must be positive")
        self._repository = repository
        self._api_limit = api_daily_limit
        self._currency = currency

    def _filter_rows(
        self,
        rows: tuple[dict[str, Any], ...],
        params: dict[str, list[str]],
    ) -> tuple[dict[str, Any], ...]:
        bookmaker = params.get("bookmaker", [""])[0].strip().casefold()
        outcome = params.get("outcome", [""])[0].strip().upper()
        league = params.get("league", [""])[0].strip().casefold()
        market = params.get("market", [""])[0].strip().casefold()
        selection = params.get("selection", [""])[0].strip().casefold()
        model_version = params.get("model_version", [""])[0].strip()
        policy_version = params.get("policy_version", [""])[0].strip()

        def keep(row: dict[str, Any]) -> bool:
            if bookmaker and bookmaker not in str(row.get("bookmaker_name") or "").casefold():
                return False
            if outcome and str(row.get("outcome") or "").upper() != outcome:
                return False
            if league and league not in str(row.get("competition_name") or "").casefold():
                return False
            if market and market not in str(row.get("market_key") or "").casefold():
                return False
            if selection and selection != str(row.get("selection") or "").casefold():
                return False
            if model_version and str(row.get("model_version") or "") != model_version:
                return False
            return not (
                policy_version
                and str(row.get("policy_version") or "") != policy_version
            )

        return tuple(row for row in rows if keep(row))

    def _filtered_rows(
        self,
        lab: str,
        params: dict[str, list[str]],
    ) -> tuple[dict[str, Any], ...]:
        rows = (
            self._repository.list_goal_picks()
            if lab == "GOAL"
            else self._repository.list_bets(lab)
        )
        return self._filter_rows(tuple(rows), params)

    def _filtered_metric_rows(
        self,
        lab: str,
        params: dict[str, list[str]],
        *,
        fallback_rows: tuple[dict[str, Any], ...],
    ) -> tuple[dict[str, Any], ...]:
        if lab == "GOAL":
            loader = getattr(self._repository, "list_all_goal_picks", None)
            if not callable(loader):
                return fallback_rows
            rows = loader()
        else:
            loader = getattr(self._repository, "list_all_bets", None)
            if not callable(loader):
                return fallback_rows
            rows = loader(lab)
        return self._filter_rows(tuple(rows), params)

    def render_goal_analytics(self) -> str:
        picks = tuple(self._repository.list_all_goal_picks())
        loader = getattr(self._repository, "list_all_goal_decision_evidence", None)
        decisions = tuple(
            loader() if callable(loader) else self._repository.list_all_goal_decisions()
        )
        snapshot = build_goal_analytics_snapshot(picks, decisions)
        return render_goal_analytics_html(snapshot)

    def render_goal_model(self, raw_query: str) -> str:
        params = parse_qs(raw_query, keep_blank_values=True)
        model_version = params.get("model_version", [""])[0].strip()
        if not model_version:
            raise ValueError("model_version is required")
        contract = self._repository.goal_model_contract(model_version)
        if contract is None:
            raise LookupError("goal model version not found")
        picks = tuple(
            row
            for row in self._repository.list_all_goal_picks()
            if str(row.get("model_version") or "") == model_version
        )
        return render_goal_model_html(contract, picks)

    def render_goal_pick(self, raw_query: str) -> str:
        params = parse_qs(raw_query, keep_blank_values=True)
        goal_pick_id = params.get("goal_pick_id", [""])[0].strip()
        if not goal_pick_id:
            raise ValueError("goal_pick_id is required")
        row = next(
            (
                item
                for item in self._repository.list_all_goal_picks()
                if str(item.get("goal_pick_id") or "") == goal_pick_id
            ),
            None,
        )
        if row is None:
            raise LookupError("goal pick not found")
        return render_goal_pick_html(row)

    def render_html(self, raw_query: str = "") -> str:
        params = parse_qs(raw_query, keep_blank_values=True)
        lab_key = params.get("lab", ["goal"])[0].strip().casefold()
        if lab_key not in LABS:
            lab_key = "goal"
        lab, title, subtitle = LABS[lab_key]
        dashboard_warnings: list[str] = []
        try:
            rows = self._filtered_rows(lab, params)
            metric_rows = self._filtered_metric_rows(
                lab,
                params,
                fallback_rows=rows,
            )
        except Exception:
            if lab_key != "goal":
                raise
            LOGGER.exception("GoalLab dashboard canonical-pick ledger query failed")
            dashboard_warnings.append("Canonical pick ledger temporarily unavailable.")
            rows = ()
            metric_rows = ()
        ledger_sort = params.get("ledger_sort", ["decision_at"])[0].strip()
        ledger_dir = params.get("ledger_dir", ["desc"])[0].strip().casefold()
        ledger_keys = {
            "match", "bookmaker_name", "market_key", "selection", "line", "model_version",
            "model_probability", "odds", "edge", "expected_value", "closing_odds", "outcome",
            "pnl_minor", "decision_at", "qualifying_candidate_count",
        }
        if ledger_sort not in ledger_keys:
            ledger_sort = "decision_at"
        if ledger_dir not in {"asc", "desc"}:
            ledger_dir = "desc"
        if ledger_sort == "match":
            rows = tuple(
                sorted(
                    rows,
                    key=lambda row: (
                        str(row.get("home_team") or "").casefold(),
                        str(row.get("away_team") or "").casefold(),
                    ),
                    reverse=ledger_dir == "desc",
                )
            )
        else:
            rows = _sort_rows(rows, ledger_sort, ledger_dir)

        settled = tuple(
            row for row in metric_rows if row.get("outcome") in {"WIN", "LOSS", "VOID"}
        )
        wins = sum(1 for row in settled if row.get("outcome") == "WIN")
        losses = sum(1 for row in settled if row.get("outcome") == "LOSS")
        pnl = sum(int(row["pnl_minor"]) for row in settled if row.get("pnl_minor") is not None)
        risked = sum(int(row["stake_minor"]) for row in settled)
        roi = None if risked == 0 else pnl / risked
        win_rate = None if wins + losses == 0 else wins / (wins + losses)
        clvs = [value for row in settled if (value := _clv_ppm(row)) is not None]
        avg_clv = None if not clvs else sum(clvs) / len(clvs)
        max_dd = _drawdown(metric_rows)
        api_used = self._repository.api_usage_today()
        model_versions = sorted(
            {
                str(row.get("model_version") or "UNRECORDED_MODEL")
                for row in metric_rows
            }
        )
        policy_versions = sorted(
            {
                str(row.get("policy_version") or "LEGACY_UNRECORDED_POLICY")
                for row in metric_rows
            }
        )
        unrecorded_policy_n = sum(
            not str(row.get("policy_version") or "").strip()
            for row in metric_rows
        )
        mixed_versions = len(model_versions) > 1 or len(policy_versions) > 1
        version_notice_html = (
            '<p class="version-warning"><b>MIXED VERSION KPI</b> '
            f'Model versions: {len(model_versions)} · policy versions: {len(policy_versions)} · '
            f'unrecorded policy rows: {unrecorded_policy_n}. '
            'Use the model/policy filters before interpreting performance.</p>'
            if metric_rows and (mixed_versions or unrecorded_policy_n)
            else (
                '<p class="version-ok"><b>SINGLE VERSION KPI</b> '
                'Current KPI cards represent one recorded model/policy regime.</p>'
                if metric_rows
                else ""
            )
        )

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

        goal_contract_cache: dict[str, dict[str, Any] | None] = {}

        def goal_contract_for(row: dict[str, Any]) -> dict[str, Any] | None:
            if lab_key != "goal":
                return None
            model_version = str(row.get("model_version") or "")
            if not model_version:
                return None
            if model_version not in goal_contract_cache:
                try:
                    goal_contract_cache[model_version] = self._repository.goal_model_contract(
                        model_version
                    )
                except Exception:
                    LOGGER.exception(
                        "GoalLab pick explanation model-contract query failed model=%s",
                        model_version,
                    )
                    goal_contract_cache[model_version] = None
            return goal_contract_cache[model_version]

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
            match_text = f'{escape(str(row.get("home_team") or "?"))} – {escape(str(row.get("away_team") or "?"))}'
            if lab_key == "goal" and row.get("goal_pick_id"):
                pick_href = "/quantlab/goal/pick?" + urlencode({"goal_pick_id": str(row["goal_pick_id"])})
                match = f'<a href="{escape(pick_href, quote=True)}">{match_text}</a>'
            else:
                match = match_text
            league_text = escape(str(row.get("competition_name") or "—"))
            line = "—" if row.get("line") is None else escape(str(row["line"]))
            if lab_key == "corner":
                note_cell = _corner_pick_note(row)
            elif lab_key == "goal" and row.get("goal_pick_id"):
                note_href = "/quantlab/goal/pick?" + urlencode(
                    {"goal_pick_id": str(row["goal_pick_id"])}
                )
                note_cell = render_goal_pick_note_html(
                    row,
                    goal_contract_for(row),
                    detail_href=note_href,
                )
            else:
                note_cell = "—"
            close_cell = (
                f'<td>{_odd(row.get("closing_odds"))}<small>audit only</small></td>'
                if lab_key == "corner"
                else f'<td>{_odd(row.get("closing_odds"))}<small>{_clv_text(_clv_ppm(row))} CLV</small></td>'
            )
            rows_html += (
                "<tr>"
                f'<td class="match"><b>{match}</b><small>{league_text} · {_time(row.get("kickoff_at"))}</small></td>'
                f'<td>{_bookmaker_badge(row.get("bookmaker_name"))}</td>'
                f'<td><b>{escape(str(row.get("market_key") or "—"))}</b>'
                f'<small>{escape(str(row.get("provider_bet_name") or "—"))}</small></td>'
                f'<td>{escape(str(row.get("selection") or "—"))}</td>'
                f"<td>{line}</td>"
                f'<td>{escape(str(row.get("model_name") or "—"))}'
                + (
                    f'<small><a href="{escape("/quantlab/goal/model?" + urlencode({"model_version": str(row.get("model_version") or "")}), quote=True)}">{escape(str(row.get("model_version") or "—"))}</a></small>'
                    if lab_key == "goal" and row.get("model_version")
                    else f'<small>{escape(str(row.get("model_version") or "—"))}</small>'
                )
                + (
                    f'<small>λH {_rate(row.get("expected_home_goals"))} · '
                    f'λA {_rate(row.get("expected_away_goals"))}</small>'
                    if lab_key == "goal"
                    else ""
                )
                + "</td>"
                f"<td>{_pct(row.get('model_probability'))}</td>"
                f"<td>{_odd(row.get('odds'))}</td>"
                f"<td>{_pct(row.get('edge'))}</td>"
                f"<td>{_pct(row.get('expected_value'))}</td>"
                + close_cell
                + f"<td>{note_cell}</td>"
                + f'<td><span class="badge {outcome_class}">{escape(outcome)}</span></td>'
                f'<td class="{pnl_class}">{_money(None if pnl_minor is None else int(pnl_minor), self._currency)}</td>'
                f"<td>{_time(row.get('decision_at'))}</td>"
                "</tr>"
            )
        if not rows_html:
            empty_text = (
                "No GoalLab canonical picks yet. Pick authority may still be OFF."
                if lab_key == "goal"
                else f"No {escape(title)} shadow bets yet. The ledger is ready for QuantLab ingestion."
            )
            rows_html = (
                '<tr><td class="empty" colspan="15">'
                f"{empty_text}"
                "</td></tr>"
            )

        goal_selected_picks_html = ""
        if lab_key == "goal":
            active_goal_picks = tuple(
                row
                for row in rows
                if str(row.get("outcome") or "PENDING").upper() == "PENDING"
            )
            selected_rows_html = ""
            for row in active_goal_picks:
                match_text = (
                    f'{escape(str(row.get("home_team") or "?"))} – '
                    f'{escape(str(row.get("away_team") or "?"))}'
                )
                pick_href = "/quantlab/goal/pick?" + urlencode(
                    {"goal_pick_id": str(row.get("goal_pick_id") or "")}
                )
                line = "" if row.get("line") is None else f" {escape(str(row['line']))}"
                pick_label = (
                    f'{escape(str(row.get("market_key") or "—"))} '
                    f'{escape(str(row.get("selection") or "—"))}{line}'
                )
                note = render_goal_pick_note_html(
                    row,
                    goal_contract_for(row),
                    detail_href=pick_href,
                )
                selected_rows_html += (
                    "<tr>"
                    f'<td class="match"><b><a href="{escape(pick_href, quote=True)}">{match_text}</a></b>'
                    f'<small>{escape(str(row.get("competition_name") or "—"))} · {_time(row.get("kickoff_at"))}</small></td>'
                    f'<td><b>{pick_label}</b><small>{_bookmaker_badge(row.get("bookmaker_name"))}</small></td>'
                    f"<td>{_pct(row.get('model_probability'))}<small>market {_pct(row.get('market_probability'))}</small></td>"
                    f"<td>λH {_rate(row.get('expected_home_goals'))}<small>λA {_rate(row.get('expected_away_goals'))}</small></td>"
                    f"<td>{_odd(row.get('odds'))}</td>"
                    f"<td>{_pct(row.get('edge'))}<small>{_pct(row.get('expected_value'))} EV</small></td>"
                    f"<td>{note}</td>"
                    f"<td>{_time(row.get('decision_at'))}</td>"
                    "</tr>"
                )
            if not selected_rows_html:
                selected_rows_html = (
                    '<tr><td class="empty" colspan="8">'
                    "Trenutno nema aktivnih GoalLab pikova za izabrane filtere."
                    "</td></tr>"
                )
            goal_selected_picks_html = (
                '<section class="table-shell context-table selected-picks">'
                '<div class="table-title"><b>Izabrani pikovi · aktivni</b>'
                f'<span>{len(active_goal_picks)} aktivnih · 📝 otvara brojčano objašnjenje</span></div>'
                '<div class="table"><table><thead><tr>'
                '<th>Meč</th><th>Pik</th><th>Model / market</th><th>Očekivani golovi</th>'
                '<th>Kvota</th><th>Edge / EV</th><th>Notes</th><th>Odluka</th>'
                f'</tr></thead><tbody>{selected_rows_html}</tbody></table></div></section>'
            )

        corner_picks_html = ""
        if lab_key == "corner":
            pending_rows = tuple(
                row
                for row in rows
                if str(row.get("outcome") or "PENDING").upper() == "PENDING"
            )
            pending_html = ""
            for row in pending_rows:
                match = (
                    f'{escape(str(row.get("home_team") or "?"))} – '
                    f'{escape(str(row.get("away_team") or "?"))}'
                )
                league_text = escape(str(row.get("competition_name") or "—"))
                line = "—" if row.get("line") is None else escape(str(row["line"]))
                pick = (
                    f'{escape(str(row.get("selection") or "—"))} {line}'
                    f'<small>{escape(str(row.get("market_key") or "—"))}</small>'
                )
                pending_html += (
                    "<tr>"
                    f'<td class="match"><b>{match}</b>'
                    f'<small>{league_text} · {_time(row.get("kickoff_at"))}</small></td>'
                    f'<td>{_bookmaker_badge(row.get("bookmaker_name"))}</td>'
                    f"<td><b>{pick}</b></td>"
                    f"<td>{_pct(row.get('model_probability'))}</td>"
                    f"<td>{_odd(row.get('odds'))}</td>"
                    f"<td>{_pct(row.get('edge'))}</td>"
                    f"<td>{_pct(row.get('expected_value'))}</td>"
                    f"<td>{_corner_pick_note(row)}</td>"
                    f"<td>{_time(row.get('decision_at'))}</td>"
                    "</tr>"
                )
            if not pending_html:
                pending_html = (
                    '<tr><td class="empty" colspan="9">'
                    "Nema aktivnih CornerLab pikova za izabrane filtere."
                    "</td></tr>"
                )
            corner_picks_html = (
                '<section class="table-shell context-table">'
                '<div class="table-title"><b>CornerLab pikovi · čekaju rezultat</b>'
                f'<span>{len(pending_rows)} active</span></div>'
                '<div class="table"><table><thead><tr>'
                '<th>Match</th><th>Bookmaker</th><th>Pick</th><th>Model p</th>'
                '<th>Odds</th><th>Edge</th><th>EV</th><th>Why</th><th>Decision</th>'
                f'</tr></thead><tbody>{pending_html}</tbody></table></div></section>'
            )

        goal_contract_html = ""
        goal_pipeline_html = ""
        if lab_key == "goal":
            try:
                contract = self._repository.goal_model_contract()
            except Exception:
                LOGGER.exception("GoalLab dashboard model-contract query failed")
                dashboard_warnings.append("DC+ model contract temporarily unavailable.")
                contract = None
            if contract is None:
                goal_contract_html = (
                    '<section class="table-shell context-table">'
                    '<div class="table-title"><b>DC+ model contract</b><span>NO ARTIFACT</span></div>'
                    '<div class="empty">No trained DC+ Structural artifact is stored yet.</div>'
                    '</section>'
                )
            else:
                training = contract.get("training_payload")
                training = training if isinstance(training, dict) else {}
                coverage = training.get("contract_coverage")
                coverage = coverage if isinstance(coverage, dict) else {}
                coverage_rows = ""
                for block_name, coverage_item in coverage.items():
                    if not isinstance(coverage_item, dict):
                        continue
                    status = str(coverage_item.get("status") or "UNKNOWN")
                    implemented = coverage_item.get("implemented")
                    pending = coverage_item.get("pending")
                    coverage_rows += (
                        "<tr>"
                        f"<td><b>{escape(str(block_name))}</b></td>"
                        f"<td>{escape(status)}</td>"
                        f"<td>{len(implemented) if isinstance(implemented, list) else 0}</td>"
                        f"<td>{len(pending) if isinstance(pending, list) else 0}</td>"
                        f"<td>{escape(str(coverage_item.get('pending_reason') or '—'))}</td>"
                        "</tr>"
                    )
                active_features = tuple(contract.get("active_feature_names") or ())
                active_feature_text = " · ".join(
                    escape(str(item)) for item in active_features
                )
                authority_raw = os.getenv(
                    "QUANTBET_QUANTLAB_GOAL_PICK_AUTHORITY", "false"
                ).strip().casefold()
                authority = authority_raw in {"1", "true", "yes", "on"}
                approved_model_version = (
                    os.getenv(
                        "QUANTBET_QUANTLAB_GOAL_APPROVED_MODEL_VERSION", ""
                    ).strip()
                    or None
                )
                current_model_version = str(contract.get("model_version") or "")
                model_approved = approved_model_version == current_model_version
                authority_text = (
                    "APPROVED"
                    if authority and model_approved
                    else "REQUESTED / MODEL NOT APPROVED"
                    if authority
                    else "OFF"
                )
                validation = contract.get("validation")
                validation = validation if isinstance(validation, dict) else {}
                validation_status = str(validation.get("status") or "PENDING")
                review_status = str(
                    validation.get("authority_review_status") or "NOT_READY"
                )
                common_n = int(validation.get("common_evaluation_size") or 0)
                comparison = validation.get("comparison")
                comparison = comparison if isinstance(comparison, dict) else {}
                ll_delta = comparison.get(
                    "dc_plus_minus_control_exact_score_mean_log_likelihood"
                )
                rmse_delta = comparison.get(
                    "dc_plus_minus_control_total_goals_rmse"
                )
                over_delta = comparison.get("dc_plus_minus_control_over25_brier")
                btts_delta = comparison.get("dc_plus_minus_control_btts_brier")
                validation_text = (
                    f"validation={validation_status} · review={review_status} · "
                    f"model approved={'YES' if model_approved else 'NO'} · "
                    f"common n={common_n} · "
                    f"ΔLL={_rate(ll_delta)} · ΔRMSE={_rate(rmse_delta)} · "
                    f"ΔO2.5 Brier={_rate(over_delta)} · ΔBTTS Brier={_rate(btts_delta)}"
                )
                goal_contract_html = (
                    '<section class="table-shell context-table">'
                    '<div class="table-title"><b>DC+ model contract / active variables</b>'
                    f'<span>{int(contract.get("active_feature_count") or 0)} active features · '
                    f'pick authority {authority_text}</span></div>'
                    '<div class="contract-summary">'
                    f'<b>{escape(str(contract.get("model_version") or "—"))}</b>'
                    f'<small>{escape(str(contract.get("feature_version") or "—"))} · '
                    f'train n={int(contract.get("training_sample_size") or 0)} · '
                    f'history n={int(contract.get("history_match_count") or 0)} · '
                    f'ρ={_rate(contract.get("rho"))} · '
                    f'policy={escape(PICK_POLICY_VERSION)}</small>'
                    f'<small>{escape(validation_text)}</small>'
                    '</div>'
                    '<div class="table"><table><thead><tr>'
                    '<th>Contract block</th><th>Status</th><th>Implemented</th>'
                    '<th>Pending</th><th>Reason</th>'
                    f'</tr></thead><tbody>{coverage_rows}</tbody></table></div>'
                    '<details class="feature-details"><summary>Exact active model features</summary>'
                    f'<div class="feature-list">{active_feature_text or "—"}</div></details>'
                    '</section>'
                )
            try:
                pipeline_rows = self._repository.list_goal_fixture_status(
                    now=datetime.now(UTC)
                )
            except Exception as exc:
                sqlstate = getattr(exc, "sqlstate", None)
                LOGGER.exception(
                    "GoalLab dashboard fixture-pipeline query failed "
                    "error_class=%s sqlstate=%s",
                    type(exc).__name__,
                    sqlstate,
                )
                dashboard_warnings.append("Upcoming GoalLab pipeline temporarily unavailable.")
                pipeline_rows = ()
            rendered_pipeline = ""
            for item in pipeline_rows:
                scope = {
                    "country": item.get("country"),
                    "competition_name": item.get("competition_name"),
                    "competition_type": item.get("competition_type"),
                    "home_team": item.get("home_team"),
                    "away_team": item.get("away_team"),
                }
                goal_allowed = goal_scope(**scope).allowed
                decision = str(item.get("decision") or "WAITING")
                reason = str(item.get("reason") or "NO_DECISION_YET")
                decision_class = (
                    "result-win" if decision == "PICK"
                    else "result-pending" if decision == "WAITING"
                    else "result-void"
                )
                match = (
                    f'{escape(str(item.get("home_team") or "?"))} – '
                    f'{escape(str(item.get("away_team") or "?"))}'
                )
                latest_pick = "—"
                if item.get("market_key"):
                    latest_pick = (
                        f'{escape(str(item.get("market_key")))} '
                        f'{escape(str(item.get("selection") or ""))} '
                        f'@ {_odd(item.get("odds"))}'
                    )
                rendered_pipeline += (
                    "<tr>"
                    f'<td class="match"><b>{match}</b><small>{escape(str(item.get("competition_name") or "—"))} · {_time(item.get("kickoff_at"))}</small></td>'
                    f'<td>{"YES" if goal_allowed else "NO"}</td>'
                    f'<td>{_time(item.get("market_captured_at"))}</td>'
                    f'<td><span class="badge {decision_class}">{escape(decision)}</span><small>{escape(reason)}</small></td>'
                    f'<td>{escape(str(item.get("model_version") or "—"))}</td>'
                    f'<td>{latest_pick}</td>'
                    f'<td>{_pct(item.get("edge"))}<small>{_pct(item.get("expected_value"))} EV</small></td>'
                    "</tr>"
                )
            if not rendered_pipeline:
                rendered_pipeline = (
                    '<tr><td class="empty" colspan="7">'
                    'No upcoming QuantLab fixtures are stored in the current lookahead window.'
                    "</td></tr>"
                )
            goal_pipeline_html = (
                '<section class="table-shell context-table">'
                '<div class="table-title"><b>Upcoming fixture / GoalLab decision pipeline</b>'
                f'<span>{len(pipeline_rows)} fixtures</span></div>'
                '<div class="table"><table><thead><tr>'
                '<th>Match</th><th>Goal scope</th><th>Last odds capture</th>'
                '<th>Decision</th><th>Model</th><th>Candidate</th><th>Edge / EV</th>'
                f'</tr></thead><tbody>{rendered_pipeline}</tbody></table></div></section>'
            )

        corner_contract_html = ""
        if lab_key == "corner":
            corner_contract_html = (
                '<section class="table-shell context-table">'
                '<div class="table-title"><b>Kako CornerLab dolazi do procene</b>'
                '<span>48 strukturnih varijabli · kvote nisu model input</span></div>'
                '<div class="corner-model-guide">'
                '<div><b>1. Korneri</b><span>Korneri za i protiv obe ekipe — poslednjih 5 i 10 utakmica, plus domaći/gostujući L5.</span></div>'
                '<div><b>2. Pritisak napada</b><span>Šutevi, šutevi u okvir, blokirani šutevi i šutevi iz kaznenog prostora.</span></div>'
                '<div><b>3. Kontrola igre</b><span>Posed, precizna dodavanja i procenat tačnih pasova.</span></div>'
                '<div><b>4. Stil napada</b><span>Ofsajdi i venue-specific forma pomažu modelu da razlikuje način na koji tim stvara pritisak.</span></div>'
                '<div><b>5. Odluka</b><span>Model prvo proceni očekivan ukupan broj kornera, zatim verovatnoću Over/Under linije. Pik postoji samo ako edge i EV oba prelaze 3%.</span></div>'
                '</div>'
                '<details class="feature-details"><summary>Tačne grupe i prozori</summary>'
                '<div class="feature-list">'
                'L5 obe ekipe: korneri za/protiv, posed, šutevi za/protiv, šutevi u okvir za/protiv, blokirani šutevi, šutevi iz kaznenog prostora, ofsajdi, precizna dodavanja, pass accuracy. '
                'L10 obe ekipe: korneri za/protiv, posed, šutevi, šutevi u okvir. '
                'Venue L5: korneri za/protiv, posed, šutevi, šutevi u okvir, šutevi iz kaznenog prostora, precizna dodavanja.'
                '</div></details>'
                '<div class="contract-summary"><small>Bet365/1xBet kvote služe samo za market probability, edge i EV. Ne ulaze u CornerLab model.</small></div>'
                '</section>'
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

        goal_research_html = ""
        if lab_key == "goal":
            decision_loader = getattr(
                self._repository,
                "list_all_goal_decision_evidence",
                getattr(self._repository, "list_all_goal_decisions", None),
            )
            try:
                research_decisions = tuple(decision_loader()) if callable(decision_loader) else ()
            except Exception as exc:
                sqlstate = getattr(exc, "sqlstate", None)
                LOGGER.exception(
                    "GoalLab dashboard research decision query failed "
                    "error_class=%s sqlstate=%s",
                    type(exc).__name__,
                    sqlstate,
                )
                dashboard_warnings.append("GoalLab research decision evidence temporarily unavailable.")
                research_decisions = ()
            snapshot = build_goal_analytics_snapshot(metric_rows, research_decisions)
            lifetime = snapshot["windows"]["lifetime"]
            audit = snapshot["integrity_audit"]
            research_table = params.get("research_table", ["model_version"])[0].strip()
            research_sort = params.get("research_sort", ["graded_n"])[0].strip()
            research_dir = params.get("research_dir", ["desc"])[0].strip().casefold()
            if research_dir not in {"asc", "desc"}:
                research_dir = "desc"

            research_specs = {
                "model_version": ("Model versions", snapshot["cohorts"]["model_version"], ("model_version",)),
                "policy_version": ("Policy versions", snapshot["cohorts"]["policy_version"], ("policy_version",)),
                "market_selection": ("Markets / selections", snapshot["cohorts"]["market_selection"], ("market_key", "selection")),
                "league": ("Leagues", snapshot["cohorts"]["league"], ("competition_name",)),
                "bookmaker": ("Bookmakers", snapshot["cohorts"]["bookmaker"], ("bookmaker_name",)),
            }
            if research_table not in {*research_specs, "calibration"}:
                research_table = "model_version"
            sortable_metrics = {
                "n", "graded_n", "wins", "losses", "voids", "win_rate_pct",
                "expected_win_rate_pct", "calibration_gap_pp", "brier_score", "log_loss",
                "roi_pct", "avg_clv_pct", "clv_n", "max_drawdown_minor", "avg_edge_pct",
                "avg_ev_pct", "sample_band", "model_version", "policy_version", "market_key",
                "selection", "competition_name", "bookmaker_name",
            }
            if research_sort not in sortable_metrics:
                research_sort = "graded_n"

            current_params = {
                key: values[0]
                for key, values in params.items()
                if values and key not in {"research_table", "research_sort", "research_dir"}
            }
            current_params["lab"] = "goal"

            def cohort_link(row: dict[str, Any], dimensions: tuple[str, ...]) -> str:
                drill = dict(current_params)
                drill.pop("ledger_sort", None)
                drill.pop("ledger_dir", None)
                if dimensions == ("model_version",):
                    drill["model_version"] = str(row.get("model_version") or "")
                elif dimensions == ("policy_version",):
                    drill["policy_version"] = str(row.get("policy_version") or "")
                elif dimensions == ("market_key", "selection"):
                    drill["market"] = str(row.get("market_key") or "")
                    drill["selection"] = str(row.get("selection") or "")
                elif dimensions == ("competition_name",):
                    drill["league"] = str(row.get("competition_name") or "")
                elif dimensions == ("bookmaker_name",):
                    drill["bookmaker"] = str(row.get("bookmaker_name") or "")
                return "/quantlab?" + urlencode({k: v for k, v in drill.items() if v}) + "#canonical-picks"

            research_tables: list[str] = []
            for table_key, (table_title, table_rows_raw, dimensions) in research_specs.items():
                table_rows = tuple(table_rows_raw)
                active_key = research_sort if research_table == table_key else "graded_n"
                active_dir = research_dir if research_table == table_key else "desc"
                if active_key not in sortable_metrics:
                    active_key = "graded_n"
                table_rows = _sort_rows(table_rows, active_key, active_dir)
                base = dict(current_params)
                base["research_table"] = table_key
                dim_headers = "".join(
                    _sortable_th(
                        dimension.replace("_", " ").title(),
                        dimension,
                        base_params=base,
                        sort_param="research_sort",
                        dir_param="research_dir",
                        active_key=active_key,
                        active_dir=active_dir,
                        anchor=f"research-{table_key}",
                    )
                    for dimension in dimensions
                )
                metric_headers = "".join(
                    _sortable_th(
                        label,
                        key,
                        base_params=base,
                        sort_param="research_sort",
                        dir_param="research_dir",
                        active_key=active_key,
                        active_dir=active_dir,
                        anchor=f"research-{table_key}",
                    )
                    for label, key in (
                        ("N", "graded_n"),
                        ("Win%", "win_rate_pct"),
                        ("ROI", "roi_pct"),
                        ("CLV", "avg_clv_pct"),
                        ("Brier", "brier_score"),
                        ("Log loss", "log_loss"),
                        ("Cal gap", "calibration_gap_pp"),
                        ("Avg edge", "avg_edge_pct"),
                        ("Avg EV", "avg_ev_pct"),
                        ("Evidence", "sample_band"),
                    )
                )
                rendered = ""
                for item in table_rows:
                    href = cohort_link(item, dimensions)
                    dim_cells = "".join(
                        f'<td><b><a href="{escape(href, quote=True)}">{escape(str(item.get(dimension) or "—"))}</a></b></td>'
                        for dimension in dimensions
                    )
                    rendered += (
                        "<tr>" + dim_cells
                        + f"<td>{item['graded_n']}</td>"
                        + f"<td>{_metric_text(item['win_rate_pct'], suffix='%')}</td>"
                        + f"<td>{_metric_text(item['roi_pct'], suffix='%', signed=True)}</td>"
                        + f"<td>{_metric_text(item['avg_clv_pct'], suffix='%', signed=True)}</td>"
                        + f"<td>{_metric_text(item['brier_score'], digits=3)}</td>"
                        + f"<td>{_metric_text(item['log_loss'], digits=3)}</td>"
                        + f"<td>{_metric_text(item['calibration_gap_pp'], suffix='pp', signed=True)}</td>"
                        + f"<td>{_metric_text(item['avg_edge_pct'], suffix='%', signed=True)}</td>"
                        + f"<td>{_metric_text(item['avg_ev_pct'], suffix='%', signed=True)}</td>"
                        + f"<td>{escape(str(item['sample_band']))}</td>"
                        + "</tr>"
                    )
                if not rendered:
                    rendered = f'<tr><td class="empty" colspan="{len(dimensions) + 10}">No settled picks for this breakdown.</td></tr>'
                research_tables.append(
                    f'<section class="research-table" id="research-{table_key}">'
                    f'<div class="table-title"><b>{escape(table_title)}</b><span>click a value → underlying picks</span></div>'
                    f'<div class="table"><table><thead><tr>{dim_headers}{metric_headers}</tr></thead>'
                    f'<tbody>{rendered}</tbody></table></div></section>'
                )

            calibration_active_key = research_sort if research_table == "calibration" else "bin"
            calibration_active_dir = research_dir if research_table == "calibration" else "asc"
            if calibration_active_key not in {"bin", "n", "expected_pct", "observed_pct", "gap_pp"}:
                calibration_active_key = "bin"
            calibration = _sort_rows(
                tuple(snapshot["calibration_bins"]),
                calibration_active_key,
                calibration_active_dir,
            )
            calibration_base = dict(current_params)
            calibration_base["research_table"] = "calibration"
            calibration_headers = "".join(
                _sortable_th(
                    label,
                    key,
                    base_params=calibration_base,
                    sort_param="research_sort",
                    dir_param="research_dir",
                    active_key=calibration_active_key,
                    active_dir=calibration_active_dir,
                    anchor="research-calibration",
                )
                for label, key in (
                    ("Bin", "bin"),
                    ("N", "n"),
                    ("Expected", "expected_pct"),
                    ("Observed", "observed_pct"),
                    ("Gap", "gap_pp"),
                )
            )
            calibration_rows = "".join(
                "<tr>"
                f"<td><b>{escape(str(item['bin']))}</b></td><td>{item['n']}</td>"
                f"<td>{_metric_text(item['expected_pct'], suffix='%')}</td>"
                f"<td>{_metric_text(item['observed_pct'], suffix='%')}</td>"
                f"<td>{_metric_text(item['gap_pp'], suffix='pp', signed=True)}</td></tr>"
                for item in calibration
            ) or '<tr><td class="empty" colspan="5">No graded picks for calibration yet.</td></tr>'

            research_cards = "".join(
                f'<div class="mini-stat"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
                for label, value in (
                    ("Audit", str(audit["status"])),
                    ("Brier", _metric_text(lifetime["brier_score"], digits=3)),
                    ("Log loss", _metric_text(lifetime["log_loss"], digits=3)),
                    ("Calibration", _metric_text(lifetime["calibration_gap_pp"], suffix="pp", signed=True)),
                    ("CLV N", str(lifetime["clv_n"])),
                    ("Violations", str(audit["violations"])),
                )
            )
            open_attr = " open" if params.get("research_table") else ""
            goal_research_html = (
                '<section class="research-shell" id="research-overview">'
                '<div class="table-title"><b>GoalLab Research / Audit</b><span>same-page research view · sortable · drillable</span></div>'
                f'<div class="mini-stats">{research_cards}</div>'
                f'<details class="research-details"{open_attr}><summary>Research breakdowns and calibration</summary>'
                + "".join(research_tables)
                + '<section class="research-table" id="research-calibration"><div class="table-title"><b>Calibration bins</b><span>selected-pick probability</span></div>'
                + f'<div class="table"><table><thead><tr>{calibration_headers}</tr></thead>'
                + f'<tbody>{calibration_rows}</tbody></table></div></section>'
                + '</details></section>'
            )

        api_pct = min(100.0, api_used / self._api_limit * 100)
        cards = (
            (
                "Canonical picks"
                if lab_key == "goal"
                else "Pikovi"
                if lab_key == "corner"
                else "Shadow bets",
                str(len(metric_rows)),
            ),
            ("Settled", str(len(settled))),
            ("P&L", _money(pnl, self._currency)),
            ("ROI", "—" if roi is None else f"{roi * 100:+.2f}%"),
            ("Win rate", "—" if win_rate is None else f"{win_rate * 100:.1f}%"),
            (
                "W-L" if lab_key == "corner" else "Avg CLV",
                f"{wins}-{losses}"
                if lab_key == "corner"
                else ("—" if avg_clv is None else f"{avg_clv / 10_000:+.2f}%"),
            ),
            ("Max drawdown", _money(max_dd, self._currency)),
            ("QuantLab API", f"{api_used:,} / {self._api_limit:,}"),
        )
        cards_html = "".join(
            f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
            for label, value in cards
        )

        lab_note = (
            "GoalLab DC+ · one canonical research pick per fixture/policy · flat stake · "
            "immutable settlement ledger · pick authority is explicit."
            if lab_key == "goal"
            else (
                "CornerLab structural model · odds are a value benchmark, not a model input · "
                "closing movement is audit-only."
                if lab_key == "corner"
                else "Bet365 + 1xBet universe · flat shadow ledger."
            )
        )
        ledger_title = (
            "GoalLab canonical picks"
            if lab_key == "goal"
            else (
                "CornerLab kompletan pick / settlement ledger"
                if lab_key == "corner"
                else f"{title} shadow ledger"
            )
        )
        header_params = {
            key: values[0]
            for key, values in params.items()
            if values and key not in {"ledger_sort", "ledger_dir"}
        }
        header_params["lab"] = lab_key
        ledger_headers = "".join(
            _sortable_th(
                label,
                key,
                base_params=header_params,
                sort_param="ledger_sort",
                dir_param="ledger_dir",
                active_key=ledger_sort,
                active_dir=ledger_dir,
                anchor="canonical-picks",
            )
            for label, key in (
                ("Match", "match"),
                ("Bookmaker", "bookmaker_name"),
                ("Market", "market_key"),
                ("Selection", "selection"),
                ("Line", "line"),
                ("Model", "model_version"),
                ("Model p", "model_probability"),
                ("Odds", "odds"),
                ("Edge", "edge"),
                ("EV", "expected_value"),
                ("Close audit", "closing_odds"),
                ("Why", "qualifying_candidate_count"),
                ("Result", "outcome"),
                ("P/L", "pnl_minor"),
                ("Decision", "decision_at"),
            )
        )

        warning_html = "".join(
            '<p class="dashboard-warning">'
            + escape(message)
            + "</p>"
            for message in dashboard_warnings
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
.dashboard-warning{{margin:0 0 10px;padding:10px 12px;border:1px solid rgba(224,111,120,.35);border-left:3px solid var(--loss);border-radius:8px;background:rgba(224,111,120,.08);color:#f0a0a7;font-size:12px}}
.version-warning,.version-ok{{margin:0 0 10px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;font-size:12px}}
.version-warning{{background:#2a2117;color:#d8b77e}}.version-ok{{background:#17251d;color:#8fd1a8}}
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
.pick-note{{position:relative}}.pick-note summary{{list-style:none;cursor:pointer;font-size:16px;width:30px;height:30px;display:flex;align-items:center;justify-content:center;border:1px solid var(--line);border-radius:8px;background:#14181b}}.pick-note summary::-webkit-details-marker{{display:none}}.note-popover{{position:absolute;z-index:8;right:0;top:35px;width:360px;max-width:75vw;padding:12px;border:1px solid #3b434a;border-radius:10px;background:#111518;box-shadow:0 12px 30px rgba(0,0,0,.35);white-space:normal;line-height:1.45}}.note-popover b,.note-popover span{{display:block}}.note-popover span{{margin-top:7px;color:#b3bbc2;font-size:11px}}.goal-note-popover{{width:640px;max-width:min(86vw,640px);max-height:70vh;overflow:auto}}.goal-note-popover p{{white-space:normal;color:#b8c0c7;font-size:11px;line-height:1.55}}.goal-note-popover h4{{margin:11px 0 5px;font-size:11px}}.goal-note-popover ul{{margin:5px 0 8px;padding-left:18px;white-space:normal;color:#b8c0c7;font-size:11px;line-height:1.5}}.note-detail-link{{display:inline-block;margin-top:8px;color:#9bc7ff;text-decoration:none;font-weight:900;font-size:11px}}.selected-picks{{margin-bottom:12px}}.corner-model-guide{{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:8px;padding:12px}}.corner-model-guide div{{border:1px solid #2d343a;border-radius:9px;background:#15191c;padding:10px}}.corner-model-guide b{{display:block;font-size:11px;margin-bottom:5px}}.corner-model-guide span{{font-size:10px;line-height:1.45;color:var(--muted)}}
.contract-summary{{padding:13px 14px;border-bottom:1px solid var(--line)}}.contract-summary small{{margin-top:6px}}
.feature-details{{padding:12px 14px;border-top:1px solid var(--line)}}.feature-details summary{{cursor:pointer;font-weight:900}}
.feature-list{{margin-top:10px;color:var(--muted);white-space:normal;line-height:1.7;font-size:11px}}
.th-wrap{{display:flex;align-items:center;justify-content:space-between;gap:7px}}.sort-tools{{display:inline-flex;gap:3px}}.sort-tools a{{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border:1px solid #3a4249;border-radius:5px;color:#9ca5ad;text-decoration:none;font-size:10px}}.sort-tools a.sort-active{{background:#e1e4e6;color:#17191b}}
.research-shell{{overflow:hidden;border:1px solid var(--line);border-radius:13px;background:var(--panel);margin-bottom:12px}}.mini-stats{{display:grid;grid-template-columns:repeat(6,minmax(110px,1fr));gap:8px;padding:12px}}.mini-stat{{padding:10px;border:1px solid #2d343a;border-radius:9px;background:#15191c}}.mini-stat small{{text-transform:uppercase;letter-spacing:.06em}}.mini-stat b{{display:block;margin-top:6px;font-size:16px}}.research-details{{border-top:1px solid var(--line)}}.research-details>summary{{cursor:pointer;padding:12px 14px;font-weight:900}}.research-table{{border-top:1px solid var(--line)}}.research-table .table{{max-height:42vh}}
footer{{margin-top:12px;color:#7f878e;font-size:11px;line-height:1.6}}
@media(max-width:1200px){{.cards{{grid-template-columns:repeat(4,1fr)}}}}@media(max-width:700px){{main{{padding:14px}}.topbar{{flex-direction:column}}.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<header class="topbar"><div><div class="eyebrow">QuantBet · QuantLab</div><h1>{escape(title)}</h1><p class="subtitle">{escape(subtitle)}</p></div><div class="readonly">● SHADOW ONLY · NO PRODUCTION WRITES</div></header>
<nav class="tabs">{tabs}</nav>
<p class="lab-note">{escape(lab_note)}</p>
{warning_html}
{version_notice_html}
<section class="cards">{cards_html}</section><div class="api-bar" title="QuantLab API budget used today"><span></span></div>
<section class="toolbar"><form method="get"><input type="hidden" name="lab" value="{escape(lab_key, quote=True)}">
<select name="bookmaker"><option value="">All bookmakers</option><option {"selected" if field("bookmaker").casefold()=="bet365" else ""}>Bet365</option><option {"selected" if field("bookmaker").casefold()=="1xbet" else ""}>1xBet</option></select>
<select name="outcome"><option value="">All outcomes</option>{''.join(f'<option {"selected" if field("outcome")==item else ""}>{item}</option>' for item in ("PENDING","WIN","LOSS","VOID"))}</select>
<input name="league" placeholder="League" value="{field("league")}"><input name="market" placeholder="Market" value="{field("market")}">
<input name="selection" placeholder="Selection" value="{field("selection")}">
<input name="model_version" placeholder="Exact model version" value="{field("model_version")}">
<input name="policy_version" placeholder="Exact policy version" value="{field("policy_version")}">
<button type="submit">Apply</button></form></section>
{goal_selected_picks_html}
{goal_pipeline_html}
{goal_research_html}
{goal_contract_html}
{corner_picks_html}
{corner_contract_html}
{card_context_html}
<section class="table-shell" id="canonical-picks"><div class="table-title"><b>{escape(ledger_title)}</b><span>{len(rows)} shown · click match for exact pick evidence</span></div><div class="table"><table><thead><tr>
{ledger_headers}
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
                allowed_paths = {
                    "/",
                    "/quantlab",
                    "/quantlab/goal/analytics",
                    "/quantlab/goal/model",
                    "/quantlab/goal/pick",
                }
                if parsed.path not in allowed_paths:
                    service._text(self, 404, "not_found\n", "text/plain; charset=utf-8")
                    return
                if not service._authorize(self):
                    return
                try:
                    if parsed.path == "/quantlab/goal/analytics":
                        body = dashboard.render_goal_analytics()
                    elif parsed.path == "/quantlab/goal/model":
                        body = dashboard.render_goal_model(parsed.query)
                    elif parsed.path == "/quantlab/goal/pick":
                        body = dashboard.render_goal_pick(parsed.query)
                    else:
                        body = dashboard.render_html(parsed.query)
                    service._text(
                        self,
                        200,
                        body,
                        "text/html; charset=utf-8",
                    )
                except (TypeError, ValueError):
                    service._text(self, 400, "invalid_filter\n", "text/plain; charset=utf-8")
                except LookupError:
                    service._text(self, 404, "not_found\n", "text/plain; charset=utf-8")
                except Exception as exc:
                    LOGGER.exception(
                        "QuantLab dashboard render failed path=%s query=%s error_class=%s",
                        parsed.path,
                        parsed.query,
                        type(exc).__name__,
                    )
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
