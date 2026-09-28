"""Read-only GoalLab analytics and drilldowns."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import math
from html import escape
from statistics import mean
from typing import Any
from urllib.parse import urlencode

from h2h.domain.settlement import realized_clv_ppm

GOALLAB_ANALYTICS_CONTRACT_VERSION = "GOALLAB_ANALYTICS_V2"


def _event_time(row: dict[str, Any]) -> datetime | None:
    value = row.get("kickoff_at") or row.get("decision_at")
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mean(values: Sequence[float]) -> float | None:
    return mean(values) if values else None


def _pct(value: float | None) -> float | None:
    return None if value is None else value * 100.0


def _sample_band(n: int) -> str:
    if n < 20:
        return "SIGNAL_ONLY"
    if n < 50:
        return "MONITOR"
    if n < 100:
        return "PROVISIONAL_EVIDENCE"
    return "STABILITY_REVIEW"


def _max_drawdown_minor(rows: Sequence[dict[str, Any]]) -> int:
    ordered = sorted(
        (row for row in rows if row.get("outcome") in {"WIN", "LOSS", "VOID"}),
        key=lambda row: (_event_time(row) or datetime.min.replace(tzinfo=UTC), str(row.get("goal_pick_id") or "")),
    )
    equity = 0
    peak = 0
    max_drawdown = 0
    for row in ordered:
        equity += int(row.get("pnl_minor") or 0)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def _realized_clv_pct(row: dict[str, Any]) -> float | None:
    closing = row.get("closing_odds")
    closing_at = row.get("closing_observed_at")
    entry_at = row.get("quote_observed_at")
    odds = row.get("odds")
    if (
        closing is None
        or odds is None
        or not isinstance(closing_at, datetime)
        or not isinstance(entry_at, datetime)
        or closing_at <= entry_at
    ):
        return None
    return realized_clv_ppm(Decimal(str(odds)), Decimal(str(closing))) / 10_000.0


def _binary_scoring(rows: Sequence[dict[str, Any]]) -> tuple[float | None, float | None]:
    scored: list[tuple[float, float]] = []
    for row in rows:
        if row.get("outcome") not in {"WIN", "LOSS"}:
            continue
        raw_probability = row.get("model_probability")
        if raw_probability is None:
            continue
        probability = min(1.0 - 1e-12, max(1e-12, float(raw_probability)))
        observed = 1.0 if row.get("outcome") == "WIN" else 0.0
        scored.append((probability, observed))
    if not scored:
        return None, None
    brier = mean((probability - observed) ** 2 for probability, observed in scored)
    log_loss = -mean(
        observed * math.log(probability)
        + (1.0 - observed) * math.log(1.0 - probability)
        for probability, observed in scored
    )
    return brier, log_loss


def calibration_bins(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if row.get("outcome") not in {"WIN", "LOSS"} or row.get("model_probability") is None:
            continue
        probability = min(1.0, max(0.0, float(row["model_probability"])))
        observed = 1.0 if row.get("outcome") == "WIN" else 0.0
        bucket = min(9, int(probability * 10))
        buckets[bucket].append((probability, observed))
    output = []
    for bucket in sorted(buckets):
        values = buckets[bucket]
        expected = mean(probability for probability, _observed in values)
        observed = mean(result for _probability, result in values)
        output.append(
            {
                "bin": f"{bucket / 10:.1f}–{(bucket + 1) / 10:.1f}",
                "n": len(values),
                "expected_pct": _pct(expected),
                "observed_pct": _pct(observed),
                "gap_pp": _pct(observed - expected),
            }
        )
    return output


def goal_pick_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    settled = tuple(row for row in rows if row.get("outcome") in {"WIN", "LOSS", "VOID"})
    graded = tuple(row for row in settled if row.get("outcome") in {"WIN", "LOSS"})
    wins = sum(row.get("outcome") == "WIN" for row in graded)
    losses = sum(row.get("outcome") == "LOSS" for row in graded)
    voids = sum(row.get("outcome") == "VOID" for row in settled)
    graded_n = wins + losses
    risked = sum(int(row.get("stake_minor") or 0) for row in graded)
    pnl_minor = sum(int(row.get("pnl_minor") or 0) for row in settled)
    observed = wins / graded_n if graded_n else None
    model_probabilities = [
        float(row["model_probability"])
        for row in graded
        if row.get("model_probability") is not None
    ]
    expected = _mean(model_probabilities)
    brier, log_loss = _binary_scoring(graded)
    clv_values = [
        value
        for row in rows
        if (value := _realized_clv_pct(row)) is not None
    ]
    return {
        "n": len(settled),
        "graded_n": graded_n,
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "win_rate_pct": _pct(observed),
        "expected_win_rate_pct": _pct(expected),
        "calibration_gap_pp": (
            _pct(observed - expected)
            if observed is not None and expected is not None
            else None
        ),
        "brier_score": brier,
        "log_loss": log_loss,
        "pnl_minor": pnl_minor,
        "roi_pct": _pct(pnl_minor / risked) if risked else None,
        "max_drawdown_minor": _max_drawdown_minor(settled),
        "clv_n": len(clv_values),
        "avg_clv_pct": _mean(clv_values),
        "closing_coverage_pct": _pct(len(clv_values) / len(rows)) if rows else None,
        "avg_odds": _mean(
            [float(row["odds"]) for row in settled if row.get("odds") is not None]
        ),
        "avg_edge_pct": _pct(
            _mean([float(row["edge"]) for row in settled if row.get("edge") is not None])
        ),
        "avg_ev_pct": _pct(
            _mean(
                [
                    float(row["expected_value"])
                    for row in settled
                    if row.get("expected_value") is not None
                ]
            )
        ),
        "sample_band": _sample_band(graded_n),
    }


def _cohorts(
    rows: Sequence[dict[str, Any]],
    dimensions: tuple[str, ...],
) -> list[dict[str, Any]]:
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
    return sorted(
        output,
        key=lambda row: (
            -int(row["graded_n"]),
            *(str(row[dimension]) for dimension in dimensions),
        ),
    )


def _decision_funnel(decisions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in decisions:
        decision = str(row.get("decision") or "UNKNOWN")
        reason = str(row.get("reason") or "UNKNOWN")
        key = (decision, reason)
        bucket = grouped.setdefault(
            key,
            {"decision": decision, "reason": reason, "rows": 0, "fixtures": set()},
        )
        bucket["rows"] += 1
        bucket["fixtures"].add(str(row.get("fixture_id") or ""))
    result = []
    for item in grouped.values():
        result.append(
            {
                "decision": item["decision"],
                "reason": item["reason"],
                "rows": item["rows"],
                "fixture_count": len(item["fixtures"]),
            }
        )
    return sorted(
        result,
        key=lambda row: (-int(row["rows"]), row["decision"], row["reason"]),
    )


def _decision_models(decisions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in decisions:
        model = str(row.get("model_version") or "NO_MODEL_ARTIFACT")
        policy = str(row.get("policy_version") or "UNRECORDED_POLICY")
        key = (model, policy)
        item = grouped.setdefault(
            key,
            {
                "model_version": model,
                "policy_version": policy,
                "rows": 0,
                "pick_rows": 0,
                "fixtures": set(),
            },
        )
        item["rows"] += 1
        item["pick_rows"] += int(row.get("decision") == "PICK")
        item["fixtures"].add(str(row.get("fixture_id") or ""))
    return sorted(
        (
            {
                "model_version": item["model_version"],
                "policy_version": item["policy_version"],
                "rows": item["rows"],
                "pick_rows": item["pick_rows"],
                "fixture_count": len(item["fixtures"]),
            }
            for item in grouped.values()
        ),
        key=lambda row: (-int(row["rows"]), row["model_version"]),
    )


def _research_integrity_audit(
    picks: Sequence[dict[str, Any]],
    decisions: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    decision_ids = {str(row.get("decision_id") or "") for row in decisions}
    canonical_keys: set[tuple[str, str]] = set()
    duplicate_keys: set[tuple[str, str]] = set()
    missing_feature_payload = 0
    missing_source_decision = 0
    missing_model_version = 0
    invalid_probability = 0
    for row in picks:
        key = (
            str(row.get("fixture_id") or ""),
            str(row.get("policy_version") or row.get("pick_policy_version") or ""),
        )
        if key in canonical_keys:
            duplicate_keys.add(key)
        canonical_keys.add(key)
        if not isinstance(row.get("feature_payload"), dict) or not row.get("feature_payload"):
            missing_feature_payload += 1
        source_decision_id = str(row.get("source_decision_id") or "")
        if source_decision_id and source_decision_id not in decision_ids:
            missing_source_decision += 1
        if not row.get("model_version"):
            missing_model_version += 1
        probability = row.get("model_probability")
        if probability is None or not 0.0 < float(probability) < 1.0:
            invalid_probability += 1
    violations = (
        len(duplicate_keys)
        + missing_feature_payload
        + missing_source_decision
        + missing_model_version
        + invalid_probability
    )
    return {
        "status": "PASS" if violations == 0 else "FAIL",
        "pick_count": len(picks),
        "decision_count": len(decisions),
        "duplicate_canonical_keys": len(duplicate_keys),
        "missing_feature_payload": missing_feature_payload,
        "missing_source_decision": missing_source_decision,
        "missing_model_version": missing_model_version,
        "invalid_model_probability": invalid_probability,
        "violations": violations,
    }


def build_goal_analytics_snapshot(
    picks: Sequence[dict[str, Any]],
    decisions: Sequence[dict[str, Any]],
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    def since(rows: Sequence[dict[str, Any]], days: int) -> tuple[dict[str, Any], ...]:
        cutoff = now - timedelta(days=days)
        return tuple(
            row
            for row in rows
            if (event_at := _event_time(row)) is not None and cutoff <= event_at <= now
        )

    weekly: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in picks:
        event_at = _event_time(row)
        if event_at is None:
            continue
        year, week, _ = event_at.isocalendar()
        weekly[f"{year}-W{week:02d}"].append(row)

    return {
        "contract_version": GOALLAB_ANALYTICS_CONTRACT_VERSION,
        "generated_at": now.isoformat(),
        "windows": {
            "lifetime": goal_pick_metrics(picks),
            "last_30d": goal_pick_metrics(since(picks, 30)),
            "last_7d": goal_pick_metrics(since(picks, 7)),
        },
        "weekly": [
            {"week": week, **goal_pick_metrics(weekly[week])}
            for week in sorted(weekly, reverse=True)
        ],
        "calibration_bins": calibration_bins(picks),
        "integrity_audit": _research_integrity_audit(picks, decisions),
        "cohorts": {
            "model_version": _cohorts(picks, ("model_version",)),
            "policy_version": _cohorts(picks, ("policy_version",)),
            "market_selection": _cohorts(picks, ("market_key", "selection")),
            "bookmaker": _cohorts(picks, ("bookmaker_name",)),
            "league": _cohorts(picks, ("competition_name",)),
        },
        "decision_funnel": _decision_funnel(decisions),
        "decision_models": _decision_models(decisions),
    }


def _fmt(value: Any, suffix: str = "", *, signed: bool = False) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        prefix = "+" if signed and value > 0 else ""
        return f"{prefix}{value:.2f}{suffix}"
    return f"{value}{suffix}"


def _metrics_table(
    title: str,
    rows: Sequence[dict[str, Any]],
    dimensions: tuple[str, ...],
    *,
    model_links: bool = False,
) -> str:
    headers = "".join(f"<th>{escape(name)}</th>" for name in dimensions)
    body = []
    for row in rows:
        cells = []
        for name in dimensions:
            raw = str(row.get(name) or "—")
            if model_links and name == "model_version" and raw not in {"—", "NO_MODEL_ARTIFACT"}:
                href = "/quantlab/goal/model?" + urlencode({"model_version": raw})
                cells.append(
                    f'<td><b><a href="{escape(href, quote=True)}">{escape(raw)}</a></b></td>'
                )
            else:
                cells.append(f"<td><b>{escape(raw)}</b></td>")
        body.append(
            "<tr>"
            + "".join(cells)
            + f"<td>{row['n']}</td>"
            + f"<td>{row['wins']}-{row['losses']}-{row['voids']}</td>"
            + f"<td>{_fmt(row['win_rate_pct'], '%')}</td>"
            + f"<td>{_fmt(row['expected_win_rate_pct'], '%')}</td>"
            + f"<td>{_fmt(row['calibration_gap_pp'], 'pp', signed=True)}</td>"
            + f"<td>{_fmt(row['roi_pct'], '%', signed=True)}</td>"
            + f"<td>{_fmt(row['avg_edge_pct'], '%', signed=True)}</td>"
            + f"<td>{_fmt(row['avg_ev_pct'], '%', signed=True)}</td>"
            + f"<td>{escape(str(row['sample_band']))}</td>"
            + "</tr>"
        )
    if not body:
        body.append(
            f'<tr><td class="empty" colspan="{len(dimensions) + 9}">No settled GoalLab picks yet.</td></tr>'
        )
    return (
        '<section class="panel"><h2>'
        + escape(title)
        + '</h2><div class="scroll"><table><thead><tr>'
        + headers
        + "<th>N</th><th>W-L-V</th><th>Win%</th><th>Exp%</th><th>Cal gap</th>"
        + "<th>ROI</th><th>Avg edge</th><th>Avg EV</th><th>Evidence</th>"
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div></section>"
    )


def render_goal_analytics_html(snapshot: dict[str, Any]) -> str:
    lifetime = snapshot["windows"]["lifetime"]
    cards = "".join(
        f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
        for label, value in (
            ("Settled", str(lifetime["n"])),
            ("W-L-V", f"{lifetime['wins']}-{lifetime['losses']}-{lifetime['voids']}"),
            ("Win rate", _fmt(lifetime["win_rate_pct"], "%")),
            ("Expected", _fmt(lifetime["expected_win_rate_pct"], "%")),
            ("Calibration", _fmt(lifetime["calibration_gap_pp"], "pp", signed=True)),
            ("ROI", _fmt(lifetime["roi_pct"], "%", signed=True)),
            ("Avg edge", _fmt(lifetime["avg_edge_pct"], "%", signed=True)),
            ("Avg EV", _fmt(lifetime["avg_ev_pct"], "%", signed=True)),
        )
    )

    funnel_rows = "".join(
        "<tr>"
        f"<td><b>{escape(str(row['decision']))}</b></td>"
        f"<td>{escape(str(row['reason']))}</td>"
        f"<td>{row['fixture_count']}</td><td>{row['rows']}</td>"
        "</tr>"
        for row in snapshot["decision_funnel"]
    ) or '<tr><td colspan="4" class="empty">No DC+ decision evidence yet.</td></tr>'

    model_decision_rows = "".join(
        "<tr>"
        + (
            f'<td><b><a href="/quantlab/goal/model?{escape(urlencode({"model_version": row["model_version"]}), quote=True)}">'
            f'{escape(str(row["model_version"]))}</a></b></td>'
            if row["model_version"] != "NO_MODEL_ARTIFACT"
            else '<td><b>NO_MODEL_ARTIFACT</b></td>'
        )
        + f"<td>{escape(str(row['policy_version']))}</td>"
        + f"<td>{row['fixture_count']}</td><td>{row['rows']}</td><td>{row['pick_rows']}</td>"
        + "</tr>"
        for row in snapshot["decision_models"]
    ) or '<tr><td colspan="5" class="empty">No DC+ model decision regimes yet.</td></tr>'

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>GoalLab Analytics</title>
<style>
:root{{--bg:#0b0d10;--panel:#14181d;--line:#29313a;--text:#e8edf2;--muted:#8e9aa6;--good:#78d6a3;--warn:#e8bd67}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px system-ui,-apple-system,sans-serif}}
main{{max-width:1500px;margin:auto;padding:24px}}a{{color:#9bc7ff;text-decoration:none}}header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:18px}}
h1{{margin:4px 0 6px}}h2{{font-size:15px;margin:0 0 12px}}small,p{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(8,minmax(120px,1fr));gap:9px;margin-bottom:16px}}
.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:10px}}.card{{padding:12px}}.card small{{display:block}}.card b{{font-size:19px}}
.panel{{padding:14px;margin-bottom:14px}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--muted);font-size:12px}}.empty{{color:var(--muted);text-align:center}}
@media(max-width:900px){{.cards{{grid-template-columns:repeat(2,1fr)}}main{{padding:12px}}}}
</style></head><body><main>
<header><div><small>{GOALLAB_ANALYTICS_CONTRACT_VERSION}</small><h1>GoalLab Analytics</h1>
<p>DC+ decision evidence + settled canonical-pick performance. Read-only.</p></div>
<div><a href="/quantlab?lab=goal">← GoalLab</a></div></header>
<section class="cards">{cards}</section>
<section class="panel"><h2>Decision funnel · DC+ Structural</h2><div class="scroll"><table><thead><tr>
<th>Decision</th><th>Reason</th><th>Fixtures</th><th>Rows</th></tr></thead>
<tbody>{funnel_rows}</tbody></table></div></section>
<section class="panel"><h2>Decision regimes · model / policy</h2><div class="scroll"><table><thead><tr>
<th>Model version</th><th>Policy</th><th>Fixtures</th><th>Rows</th><th>PICK rows</th></tr></thead>
<tbody>{model_decision_rows}</tbody></table></div></section>
{_metrics_table("Model versions · settled canonical picks", snapshot["cohorts"]["model_version"], ("model_version",), model_links=True)}
{_metrics_table("Markets / selections", snapshot["cohorts"]["market_selection"], ("market_key", "selection"))}
{_metrics_table("Leagues", snapshot["cohorts"]["league"], ("competition_name",))}
{_metrics_table("Bookmakers", snapshot["cohorts"]["bookmaker"], ("bookmaker_name",))}
{_metrics_table("Weekly stability", snapshot["weekly"], ("week",))}
</main></body></html>"""


def _flatten_features(
    payload: Any,
    *,
    prefix: str = "",
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(payload, dict):
        for key in sorted(payload):
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten_features(payload[key], prefix=child))
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            rows.extend(_flatten_features(value, prefix=f"{prefix}[{index}]"))
    else:
        rows.append((prefix or "value", "—" if payload is None else str(payload)))
    return rows


def render_goal_pick_html(row: dict[str, Any]) -> str:
    features = _flatten_features(row.get("feature_payload") or {})
    feature_rows = "".join(
        f"<tr><td><b>{escape(name)}</b></td><td>{escape(value)}</td></tr>"
        for name, value in features
    ) or '<tr><td colspan="2" class="empty">No feature payload.</td></tr>'
    rank_rows = _flatten_features(row.get("selection_rank_payload") or {})
    rank_html = "".join(
        f"<tr><td><b>{escape(name)}</b></td><td>{escape(value)}</td></tr>"
        for name, value in rank_rows
    ) or '<tr><td colspan="2" class="empty">No candidate-rank payload.</td></tr>'
    match = f"{row.get('home_team') or '?'} – {row.get('away_team') or '?'}"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>GoalLab pick</title>
<style>body{{background:#0b0d10;color:#e8edf2;font:14px system-ui;margin:0}}main{{max-width:1300px;margin:auto;padding:24px}}a{{color:#9bc7ff}}section{{background:#14181d;border:1px solid #29313a;border-radius:10px;padding:14px;margin:14px 0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;border-bottom:1px solid #29313a;text-align:left;vertical-align:top}}small,p{{color:#8e9aa6}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}.grid div{{background:#14181d;border:1px solid #29313a;border-radius:8px;padding:10px}}@media(max-width:800px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}</style>
</head><body><main><a href="/quantlab/goal/analytics">← GoalLab Analytics</a>
<h1>{escape(match)}</h1><p>{escape(str(row.get("competition_name") or "—"))} · {escape(str(row.get("model_version") or "—"))}</p>
<div class="grid">
<div><small>Pick</small><b>{escape(str(row.get("market_key") or "—"))} {escape(str(row.get("selection") or "—"))}</b></div>
<div><small>Odds</small><b>{escape(str(row.get("odds") or "—"))}</b></div>
<div><small>Model p</small><b>{escape(str(row.get("model_probability") or "—"))}</b></div>
<div><small>Market p</small><b>{escape(str(row.get("market_probability") or "—"))}</b></div>
<div><small>Edge</small><b>{escape(str(row.get("edge") or "—"))}</b></div>
<div><small>EV</small><b>{escape(str(row.get("expected_value") or "—"))}</b></div>
<div><small>λ home / away</small><b>{escape(str(row.get("expected_home_goals") or "—"))} / {escape(str(row.get("expected_away_goals") or "—"))}</b></div>
<div><small>Outcome / P&L</small><b>{escape(str(row.get("outcome") or "PENDING"))} / {escape(str(row.get("pnl_minor") or "—"))}</b></div>
</div>
<section><h2>Exact decision feature payload</h2><table><tbody>{feature_rows}</tbody></table></section>
<section><h2>Canonical candidate ranking payload</h2><table><tbody>{rank_html}</tbody></table></section>
</main></body></html>"""


def render_goal_model_html(
    contract: dict[str, Any],
    picks: Sequence[dict[str, Any]],
) -> str:
    validation = contract.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    training = contract.get("training_payload")
    training = training if isinstance(training, dict) else {}
    metrics = goal_pick_metrics(picks)
    active = tuple(contract.get("active_feature_names") or ())
    feature_rows = "".join(
        f"<tr><td>{index + 1}</td><td><b>{escape(str(name))}</b></td></tr>"
        for index, name in enumerate(active)
    ) or '<tr><td colspan="2" class="empty">No active features recorded.</td></tr>'
    pick_rows = "".join(
        "<tr>"
        f'<td><a href="/quantlab/goal/pick?{escape(urlencode({"goal_pick_id": row["goal_pick_id"]}), quote=True)}">'
        f'{escape(str(row.get("home_team") or "?"))} – {escape(str(row.get("away_team") or "?"))}</a></td>'
        f"<td>{escape(str(row.get('market_key') or '—'))} {escape(str(row.get('selection') or '—'))}</td>"
        f"<td>{escape(str(row.get('odds') or '—'))}</td><td>{escape(str(row.get('edge') or '—'))}</td>"
        f"<td>{escape(str(row.get('expected_value') or '—'))}</td><td>{escape(str(row.get('outcome') or 'PENDING'))}</td>"
        "</tr>"
        for row in picks
    ) or '<tr><td colspan="6" class="empty">No canonical picks for this model version yet.</td></tr>'
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>GoalLab model</title>
<style>body{{background:#0b0d10;color:#e8edf2;font:14px system-ui;margin:0}}main{{max-width:1400px;margin:auto;padding:24px}}a{{color:#9bc7ff}}section{{background:#14181d;border:1px solid #29313a;border-radius:10px;padding:14px;margin:14px 0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;border-bottom:1px solid #29313a;text-align:left}}small,p{{color:#8e9aa6}}.cards{{display:grid;grid-template-columns:repeat(8,1fr);gap:8px}}.cards div{{background:#14181d;border:1px solid #29313a;border-radius:8px;padding:10px}}@media(max-width:900px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}</style></head>
<body><main><a href="/quantlab/goal/analytics">← GoalLab Analytics</a>
<h1>DC+ model version</h1><p>{escape(str(contract.get("model_version") or "—"))}</p>
<div class="cards">
<div><small>Train N</small><b>{int(contract.get("training_sample_size") or 0)}</b></div>
<div><small>History N</small><b>{int(contract.get("history_match_count") or 0)}</b></div>
<div><small>Features</small><b>{int(contract.get("active_feature_count") or 0)}</b></div>
<div><small>Latent teams</small><b>{int(training.get("latent_team_count") or 0)}</b></div>
<div><small>Latent min N</small><b>{int(training.get("minimum_latent_team_matches") or 0)}</b></div>
<div><small>ρ</small><b>{escape(str(contract.get("rho") or "—"))}</b></div>
<div><small>Validation</small><b>{escape(str(validation.get("status") or "PENDING"))}</b></div>
<div><small>Review</small><b>{escape(str(validation.get("authority_review_status") or "NOT_READY"))}</b></div>
</div>
<section><h2>Settled performance for this model</h2><p>N={metrics["n"]} · W-L-V={metrics["wins"]}-{metrics["losses"]}-{metrics["voids"]} · ROI={_fmt(metrics["roi_pct"], "%", signed=True)} · calibration={_fmt(metrics["calibration_gap_pp"], "pp", signed=True)}</p></section>
<section><h2>Exact active model features</h2><table><thead><tr><th>#</th><th>Feature</th></tr></thead><tbody>{feature_rows}</tbody></table></section>
<section><h2>Canonical picks from this model</h2><table><thead><tr><th>Match</th><th>Pick</th><th>Odds</th><th>Edge</th><th>EV</th><th>Outcome</th></tr></thead><tbody>{pick_rows}</tbody></table></section>
</main></body></html>"""
