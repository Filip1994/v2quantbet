"""Continuous read-only performance analytics for the Research universe."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from html import escape
from math import sqrt
from statistics import mean, median
from typing import Any
from urllib.parse import urlencode


ANALYTICS_CONTRACT_VERSION = "RESEARCH_ANALYTICS_V2"

DIAGNOSTIC_BUCKETS = (
    "LOW_SCORING_EXTREME",
    "OTHER_EXTREME",
    "LOW_SCORING_NON_EXTREME",
    "OTHER_NON_EXTREME",
)


def diagnostic_bucket(row: dict[str, Any]) -> str:
    """Return the stable Research Analytics V2 diagnostic bucket for one row."""
    extreme = (
        float(row["expected_value"]) >= 0.30
        or float(row["edge"]) >= 0.20
    )
    low_scoring = (
        row.get("market") == "OU_25" and row.get("selection") == "UNDER"
    ) or (
        row.get("market") == "BTTS" and row.get("selection") == "NO"
    )
    if low_scoring:
        return "LOW_SCORING_EXTREME" if extreme else "LOW_SCORING_NON_EXTREME"
    return "OTHER_EXTREME" if extreme else "OTHER_NON_EXTREME"


def market_fair_probability_bucket(value: Any) -> str:
    if value is None:
        return "—"
    probability = float(value) * 100
    for low, high in (
        (25, 35),
        (35, 40),
        (40, 45),
        (45, 50),
        (50, 55),
        (55, 60),
        (60, 65),
        (65, 75),
    ):
        if low <= probability < high:
            return f"{low}–{high}%"
    if probability >= 75:
        return "75%+"
    return "<25%"


def _event_time(row: dict[str, Any]) -> datetime | None:
    value = row.get("kickoff_at") or row.get("qualified_at")
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _wilson_interval(wins: int, trials: int) -> tuple[float | None, float | None]:
    if trials <= 0:
        return None, None
    z = 1.959963984540054
    observed = wins / trials
    denominator = 1 + (z * z / trials)
    centre = (observed + (z * z / (2 * trials))) / denominator
    margin = (
        z
        * sqrt(
            (observed * (1 - observed) / trials)
            + (z * z / (4 * trials * trials))
        )
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _sample_band(n: int) -> str:
    if n < 20:
        return "SIGNAL_ONLY"
    if n < 50:
        return "MONITOR"
    if n < 100:
        return "PROVISIONAL_EVIDENCE"
    return "STABILITY_REVIEW"


def _mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return mean(materialized) if materialized else None


def _pct(value: float | None) -> float | None:
    return None if value is None else value * 100


def _version_value(row: dict[str, Any], key: str, *, missing: str) -> str:
    value = row.get(key)
    if value is None:
        return missing
    rendered = str(value).strip()
    return rendered or missing


def _version_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    model_versions = sorted(
        {
            _version_value(row, "model_version_id", missing="UNRECORDED_MODEL")
            for row in rows
        }
    )
    policy_configs = sorted(
        {
            _version_value(
                row,
                "policy_config_fingerprint",
                missing="LEGACY_UNRECORDED_POLICY",
            )
            for row in rows
        }
    )
    unrecorded_policy_n = sum(
        not str(row.get("policy_config_fingerprint") or "").strip()
        for row in rows
    )
    return {
        "model_version_count": len(model_versions),
        "policy_config_count": len(policy_configs),
        "mixed_model_versions": len(model_versions) > 1,
        "mixed_policy_configs": len(policy_configs) > 1,
        "unrecorded_policy_n": unrecorded_policy_n,
        "model_versions": model_versions,
        "policy_configs": policy_configs,
    }


def cohort_metrics(
    rows: Sequence[dict[str, Any]],
    *,
    fixed_stake_minor: int,
) -> dict[str, Any]:
    settled = tuple(row for row in rows if row.get("outcome") in {"WIN", "LOSS", "VOID"})
    graded = tuple(row for row in settled if row.get("outcome") in {"WIN", "LOSS"})
    wins = sum(row["outcome"] == "WIN" for row in settled)
    losses = sum(row["outcome"] == "LOSS" for row in settled)
    voids = sum(row["outcome"] == "VOID" for row in settled)
    graded_n = wins + losses

    observed = wins / graded_n if graded_n else None
    expected = _mean(float(row["model_probability"]) for row in graded)
    calibration_gap = (
        observed - expected if observed is not None and expected is not None else None
    )
    pnl_minor = sum(int(row.get("pnl_minor") or 0) for row in settled)
    roi = (
        pnl_minor / (fixed_stake_minor * graded_n)
        if fixed_stake_minor > 0 and graded_n
        else None
    )

    clv_values = [
        int(row["clv_ppm"])
        for row in settled
        if row.get("clv_ppm") is not None
    ]
    win_low, win_high = _wilson_interval(wins, graded_n)

    return {
        "n": len(settled),
        "graded_n": graded_n,
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "win_rate_pct": _pct(observed),
        "expected_win_rate_pct": _pct(expected),
        "calibration_gap_pp": _pct(calibration_gap),
        "win_rate_wilson_95_low_pct": _pct(win_low),
        "win_rate_wilson_95_high_pct": _pct(win_high),
        "flat_pnl_minor": pnl_minor,
        "roi_pct": _pct(roi),
        "avg_entry_odds": _mean(float(row["odds"]) for row in settled),
        "avg_model_probability_pct": _pct(
            _mean(float(row["model_probability"]) for row in settled)
        ),
        "avg_market_fair_probability_pct": _pct(
            _mean(float(row["market_fair_probability"]) for row in settled)
        ),
        "avg_edge_pct": _pct(_mean(float(row["edge"]) for row in settled)),
        "avg_ev_pct": _pct(_mean(float(row["expected_value"]) for row in settled)),
        "clv_count": len(clv_values),
        "clv_coverage_pct": (
            len(clv_values) / len(settled) * 100 if settled else None
        ),
        "avg_clv_pct": (
            mean(clv_values) / 10_000 if clv_values else None
        ),
        "median_clv_pct": (
            median(clv_values) / 10_000 if clv_values else None
        ),
        "positive_clv_rate_pct": (
            sum(value > 0 for value in clv_values) / len(clv_values) * 100
            if clv_values
            else None
        ),
        "sample_band": _sample_band(graded_n),
    }


def _cohort_rows(
    rows: Sequence[dict[str, Any]],
    dimensions: tuple[str, ...],
    *,
    fixed_stake_minor: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)

    def dimension_value(row: dict[str, Any], dimension: str) -> str:
        if dimension == "policy_config_fingerprint":
            return _version_value(
                row,
                dimension,
                missing="LEGACY_UNRECORDED_POLICY",
            )
        if dimension == "model_version_id":
            return _version_value(row, dimension, missing="UNRECORDED_MODEL")
        return str(row.get(dimension) or "—")

    for row in rows:
        key = tuple(dimension_value(row, dimension) for dimension in dimensions)
        grouped[key].append(row)

    result: list[dict[str, Any]] = []
    for key, cohort in grouped.items():
        item = {dimension: value for dimension, value in zip(dimensions, key, strict=True)}
        item.update(cohort_metrics(cohort, fixed_stake_minor=fixed_stake_minor))
        result.append(item)

    return sorted(
        result,
        key=lambda item: (
            -int(item["graded_n"]),
            *(str(item[dimension]) for dimension in dimensions),
        ),
    )


def _diagnostic_rows(
    rows: Sequence[dict[str, Any]],
    *,
    fixed_stake_minor: int,
) -> list[dict[str, Any]]:
    output = []
    for name in DIAGNOSTIC_BUCKETS:
        cohort = tuple(row for row in rows if diagnostic_bucket(row) == name)
        item = {"diagnostic": name}
        item.update(cohort_metrics(cohort, fixed_stake_minor=fixed_stake_minor))
        output.append(item)
    return output


def build_research_analytics_snapshot(
    rows: Sequence[dict[str, Any]],
    *,
    fixed_stake_minor: int,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    settled = tuple(row for row in rows if row.get("outcome") != "PENDING")
    dated = tuple((row, _event_time(row)) for row in settled)

    def since(days: int) -> tuple[dict[str, Any], ...]:
        cutoff = now - timedelta(days=days)
        return tuple(
            row
            for row, event_at in dated
            if event_at is not None and cutoff <= event_at <= now
        )

    weekly: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row, event_at in dated:
        if event_at is None:
            continue
        iso_year, iso_week, _ = event_at.isocalendar()
        weekly[f"{iso_year}-W{iso_week:02d}"].append(row)

    cohort_dimensions = {
        "market_selection": ("market", "selection"),
        "model_probability_bucket": ("probability_bucket",),
        "market_fair_probability_bucket": ("market_fair_probability_bucket",),
        "ev_bucket": ("ev_bucket",),
        "odds_bucket": ("odds_bucket",),
        "disposition": ("disposition",),
        "bookmaker": ("bookmaker",),
        "league": ("competition_name",),
        "league_season": ("competition_name", "league_id", "season"),
        "freshness": ("freshness",),
        "model_version": ("model_version_id",),
        "policy_config": ("policy_config_fingerprint",),
        "model_policy": ("model_version_id", "policy_config_fingerprint"),
        "decision_contract": (
            "model_version_id",
            "prediction_method_version",
            "devig_method_version",
            "policy_config_fingerprint",
        ),
        "market_selection_model_probability": (
            "market",
            "selection",
            "probability_bucket",
        ),
        "market_selection_market_fair_probability": (
            "market",
            "selection",
            "market_fair_probability_bucket",
        ),
        "market_selection_ev": ("market", "selection", "ev_bucket"),
        "market_selection_odds": ("market", "selection", "odds_bucket"),
        "production_filter_cube": (
            "market",
            "selection",
            "probability_bucket",
            "market_fair_probability_bucket",
            "ev_bucket",
            "odds_bucket",
        ),
    }

    return {
        "contract_version": ANALYTICS_CONTRACT_VERSION,
        "generated_at": now.isoformat(),
        "definitions": {
            "universe": (
                "Canonical Research final-gate candidates, one candidate per fixture; "
                "analytics use settled rows only."
            ),
            "roi": (
                "Flat P/L divided by fixed stake times graded WIN/LOSS count; "
                "voids are reported but excluded from the ROI denominator."
            ),
            "calibration_gap": "Observed win rate minus mean model probability, percentage points.",
            "clv": "Research close must be a later stored same-series/source pre-kickoff quote.",
            "versioning": (
                "Overall windows may combine versions; use model/policy/decision-contract "
                "cohorts for regime-specific conclusions. Legacy policy rows are never inferred."
            ),
            "sample_bands": {
                "SIGNAL_ONLY": "<20 graded",
                "MONITOR": "20–49 graded",
                "PROVISIONAL_EVIDENCE": "50–99 graded",
                "STABILITY_REVIEW": "100+ graded",
            },
        },
        "version_summary": _version_summary(settled),
        "windows": {
            "lifetime": cohort_metrics(settled, fixed_stake_minor=fixed_stake_minor),
            "last_30d": cohort_metrics(since(30), fixed_stake_minor=fixed_stake_minor),
            "last_7d": cohort_metrics(since(7), fixed_stake_minor=fixed_stake_minor),
        },
        "weekly": [
            {
                "week": week,
                **cohort_metrics(
                    weekly[week],
                    fixed_stake_minor=fixed_stake_minor,
                ),
            }
            for week in sorted(weekly, reverse=True)
        ],
        "diagnostics": _diagnostic_rows(
            settled,
            fixed_stake_minor=fixed_stake_minor,
        ),
        "cohorts": {
            name: _cohort_rows(
                settled,
                dimensions,
                fixed_stake_minor=fixed_stake_minor,
            )
            for name, dimensions in cohort_dimensions.items()
        },
    }


def _fmt(value: Any, suffix: str = "", signed: bool = False) -> str:
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
    dimension_links: dict[str, str] | None = None,
    dimension_link_params: dict[str, tuple[str, ...]] | None = None,
    dimension_labels: dict[str, str] | None = None,
) -> str:
    dimension_headers = "".join(
        f"<th>{escape((dimension_labels or {}).get(name, name))}</th>"
        for name in dimensions
    )
    body = []
    for row in rows:
        cells = []
        for name in dimensions:
            raw_value = str(row.get(name, "—"))
            value = escape(raw_value)
            base_path = (dimension_links or {}).get(name)
            if base_path:
                param_names = (dimension_link_params or {}).get(name, (name,))
                href = base_path + "?" + urlencode(
                    {
                        param_name: str(row.get(param_name, "—"))
                        for param_name in param_names
                    }
                )
                cells.append(
                    f'<td><b><a class="dimension-link" href="{escape(href, quote=True)}">'
                    f"{value}</a></b></td>"
                )
            else:
                cells.append(f"<td><b>{value}</b></td>")
        dims = "".join(cells)
        body.append(
            "<tr>"
            + dims
            + f"<td>{row['n']}</td>"
            + f"<td>{row['wins']}-{row['losses']}-{row['voids']}</td>"
            + f"<td>{_fmt(row['win_rate_pct'], '%')}</td>"
            + f"<td>{_fmt(row['expected_win_rate_pct'], '%')}</td>"
            + f"<td>{_fmt(row['calibration_gap_pp'], 'pp', signed=True)}</td>"
            + f"<td>{_fmt(row['roi_pct'], '%', signed=True)}</td>"
            + f"<td>{_fmt(row['avg_clv_pct'], '%', signed=True)}</td>"
            + f"<td>{_fmt(row['median_clv_pct'], '%', signed=True)}</td>"
            + f"<td>{_fmt(row['positive_clv_rate_pct'], '%')}</td>"
            + f"<td>{escape(str(row['sample_band']))}</td>"
            + "</tr>"
        )
    if not body:
        body.append(
            f'<tr><td colspan="{len(dimensions) + 10}" class="empty">No settled rows.</td></tr>'
        )
    return (
        '<section class="panel"><h2>'
        + escape(title)
        + '</h2><div class="scroll"><table><thead><tr>'
        + dimension_headers
        + "<th>N</th><th>W-L-V</th><th>Win%</th><th>Exp%</th><th>Cal gap</th>"
        + "<th>ROI</th><th>Avg CLV</th><th>Med CLV</th><th>+CLV%</th><th>Evidence</th>"
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div></section>"
    )


def render_research_analytics_html(snapshot: dict[str, Any]) -> str:
    windows = snapshot["windows"]
    lifetime = windows["lifetime"]
    version_summary = snapshot["version_summary"]
    mixed_versions = (
        version_summary["mixed_model_versions"]
        or version_summary["mixed_policy_configs"]
        or version_summary["unrecorded_policy_n"] > 0
    )
    version_notice = (
        '<div class="version-warning"><b>MIXED / LEGACY VERSION AGGREGATE</b>'
        f'<span>model versions={version_summary["model_version_count"]} · '
        f'policy configs={version_summary["policy_config_count"]} · '
        f'unrecorded policy rows={version_summary["unrecorded_policy_n"]}. '
        'Use the version cohorts below before interpreting lifetime performance.</span></div>'
        if mixed_versions
        else '<div class="version-ok"><b>SINGLE VERSION REGIME</b>'
        '<span>Lifetime cards represent one recorded model/policy regime.</span></div>'
    )
    cards = "".join(
        (
            f'<div class="card"><small>{escape(label)}</small><b>{escape(value)}</b></div>'
        )
        for label, value in (
            ("Settled", str(lifetime["n"])),
            ("W-L-V", f"{lifetime['wins']}-{lifetime['losses']}-{lifetime['voids']}"),
            ("Win rate", _fmt(lifetime["win_rate_pct"], "%")),
            ("Expected", _fmt(lifetime["expected_win_rate_pct"], "%")),
            ("Calibration", _fmt(lifetime["calibration_gap_pp"], "pp", signed=True)),
            ("ROI", _fmt(lifetime["roi_pct"], "%", signed=True)),
            ("Avg CLV", _fmt(lifetime["avg_clv_pct"], "%", signed=True)),
            ("+CLV", _fmt(lifetime["positive_clv_rate_pct"], "%")),
        )
    )

    weekly = _metrics_table("Weekly stability", snapshot["weekly"], ("week",))
    diagnostics = _metrics_table(
        "Low-scoring extreme-value diagnostic",
        snapshot["diagnostics"],
        ("diagnostic",),
    )
    league_seasons = _metrics_table(
        "Leagues · all retrains combined",
        snapshot["cohorts"]["league_season"],
        ("competition_name", "league_id", "season"),
        dimension_links={"competition_name": "/research/analytics/league"},
        dimension_link_params={"competition_name": ("league_id", "season")},
        dimension_labels={
            "competition_name": "League",
            "league_id": "League ID",
            "season": "Season",
        },
    )
    model_versions = _metrics_table(
        "Model versions · individual retrains",
        snapshot["cohorts"]["model_version"],
        ("model_version_id",),
        dimension_links={"model_version_id": "/research/analytics/model"},
    )
    policy_configs = _metrics_table(
        "Policy configurations",
        snapshot["cohorts"]["policy_config"],
        ("policy_config_fingerprint",),
    )
    model_policy = _metrics_table(
        "Model × policy regimes",
        snapshot["cohorts"]["model_policy"],
        ("model_version_id", "policy_config_fingerprint"),
        dimension_links={"model_version_id": "/research/analytics/model"},
    )
    decision_contract = _metrics_table(
        "Full decision contract",
        snapshot["cohorts"]["decision_contract"],
        (
            "model_version_id",
            "prediction_method_version",
            "devig_method_version",
            "policy_config_fingerprint",
        ),
        dimension_links={"model_version_id": "/research/analytics/model"},
    )
    market_selection = _metrics_table(
        "Market × selection",
        snapshot["cohorts"]["market_selection"],
        ("market", "selection"),
    )
    model_probability = _metrics_table(
        "Model probability buckets",
        snapshot["cohorts"]["model_probability_bucket"],
        ("probability_bucket",),
    )
    fair_probability = _metrics_table(
        "Market fair probability buckets",
        snapshot["cohorts"]["market_fair_probability_bucket"],
        ("market_fair_probability_bucket",),
    )
    ev = _metrics_table(
        "EV buckets",
        snapshot["cohorts"]["ev_bucket"],
        ("ev_bucket",),
    )
    odds = _metrics_table(
        "Odds buckets",
        snapshot["cohorts"]["odds_bucket"],
        ("odds_bucket",),
    )
    cube = _metrics_table(
        "Production-filter evidence cube",
        snapshot["cohorts"]["production_filter_cube"],
        (
            "market",
            "selection",
            "probability_bucket",
            "market_fair_probability_bucket",
            "ev_bucket",
            "odds_bucket",
        ),
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantBet Research Analytics V2</title>
<style>
:root{{--bg:#111315;--panel:#181b1f;--line:#30363d;--text:#eceff1;--muted:#9299a1}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);
font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1920px;margin:auto;padding:24px}}
header{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}}
h1{{margin:0;font-size:25px}}h2{{font-size:15px;margin:0 0 12px}}p,small{{color:var(--muted)}}
a{{color:#d8dcdf}}.dimension-link{{text-decoration:none;border-bottom:1px dotted #778089}}
.dimension-link:hover{{color:#fff;border-bottom-color:#fff}}.cards{{display:grid;grid-template-columns:repeat(8,minmax(120px,1fr));
gap:9px;margin:15px 0}}.card,.panel{{background:var(--panel);border:1px solid var(--line);
border-radius:12px}}.card{{padding:13px}}.card small{{text-transform:uppercase;font-size:10px;
letter-spacing:.08em}}.card b{{display:block;font-size:20px;margin-top:7px}}.panel{{padding:14px;
margin:12px 0}}.scroll{{overflow:auto;max-height:62vh}}table{{width:100%;
border-collapse:collapse;font-size:12px}}th,td{{padding:9px 10px;border-bottom:1px solid #272c31;
white-space:nowrap;text-align:left}}th{{position:sticky;top:0;background:#1b1f23;color:#9aa1a8;
font-size:10px;text-transform:uppercase;letter-spacing:.05em}}.empty{{color:var(--muted);
text-align:center}}.definition{{padding:12px 14px;border:1px solid var(--line);
border-radius:10px;color:var(--muted);font-size:12px}}.version-warning,.version-ok{{
display:flex;gap:10px;align-items:center;padding:11px 14px;margin:12px 0;border-radius:10px;
border:1px solid var(--line);font-size:12px}}.version-warning{{background:#2a2117}}
.version-warning b{{color:#f0b36a}}.version-ok{{background:#17251d}}.version-ok b{{color:#79c995}}
.version-warning span,.version-ok span{{color:var(--muted)}}@media(max-width:900px){{
.cards{{grid-template-columns:repeat(2,1fr)}}main{{padding:14px}}}}
</style></head><body><main>
<header><div><small>{ANALYTICS_CONTRACT_VERSION}</small><h1>Research Analytics V2</h1>
<p>Continuous settled-performance matrix. Read-only; no Production selection changes.</p></div>
<div><a href="/research">← Research Board</a> ·
<a href="/research/analytics.json">JSON</a></div></header>
<div class="definition">Universe: {escape(snapshot['definitions']['universe'])}
ROI: {escape(snapshot['definitions']['roi'])}<br>
Versioning: {escape(snapshot['definitions']['versioning'])}</div>
{version_notice}
<section class="cards">{cards}</section>
{league_seasons}{model_versions}{policy_configs}{model_policy}{decision_contract}
{diagnostics}{market_selection}{model_probability}{fair_probability}{ev}{odds}{weekly}{cube}
</main></body></html>"""
