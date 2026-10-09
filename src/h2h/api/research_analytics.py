"""Continuous read-only performance analytics for the Research universe."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from html import escape
from math import sqrt
from statistics import mean, median, stdev
from typing import Any
from urllib.parse import parse_qs, urlencode

from h2h.production_buckets import (
    PRODUCTION_BUCKET_SPECS,
    RESEARCH_BTTS_NO_ODDS_2_01_2_50,
    RESEARCH_LOW_SCORING_NON_EXTREME,
    RESEARCH_OU_UNDER_EDGE_10_15,
    RESEARCH_OU_UNDER_EDGE_20_30,
    is_retired_research_segment,
    n_roi_priority_score,
)


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
    """Evidence maturity for ROI-led pruning; never an automatic betting decision."""
    if n < 100:
        return "COLLECT"
    if n < 250:
        return "WATCH"
    if n < 500:
        return "SOFT_REVIEW"
    if n < 1000:
        return "DECISION_GRADE"
    return "MATURE"


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
    per_bet_returns = (
        [
            int(row.get("pnl_minor") or 0) / fixed_stake_minor
            for row in graded
        ]
        if fixed_stake_minor > 0
        else []
    )
    if len(per_bet_returns) >= 2:
        roi_se = stdev(per_bet_returns) / sqrt(len(per_bet_returns))
        roi_95_low = (mean(per_bet_returns) - 1.959963984540054 * roi_se) * 100
        roi_95_high = (mean(per_bet_returns) + 1.959963984540054 * roi_se) * 100
    else:
        roi_95_low = None
        roi_95_high = None

    graded_by_time = sorted(
        graded,
        key=lambda row: _event_time(row) or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )

    def trailing_roi(limit: int) -> float | None:
        if fixed_stake_minor <= 0 or len(graded_by_time) < limit:
            return None
        sample = graded_by_time[:limit]
        return (
            sum(int(row.get("pnl_minor") or 0) for row in sample)
            / (fixed_stake_minor * limit)
            * 100
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
        "roi_95_low_pct": roi_95_low,
        "roi_95_high_pct": roi_95_high,
        "roi_last_100_pct": trailing_roi(100),
        "roi_last_250_pct": trailing_roi(250),
        "roi_last_500_pct": trailing_roi(500),
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

    settled_all = tuple(row for row in rows if row.get("outcome") != "PENDING")
    settled_active = tuple(
        row for row in settled_all if not is_retired_research_segment(row)
    )
    dated = tuple((row, _event_time(row)) for row in settled_active)

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
        "edge_bucket": ("edge_bucket",),
        "odds_bucket": ("odds_bucket",),
        "time_to_kickoff_bucket": ("time_to_kickoff_bucket",),
        "disposition": ("disposition",),
        "bookmaker": ("bookmaker",),
        "league": ("competition_name", "league_id"),
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
        "market_selection_edge": ("market", "selection", "edge_bucket"),
        "market_selection_odds": ("market", "selection", "odds_bucket"),
        "league_market": ("competition_name", "league_id", "market", "selection"),
    }

    return {
        "contract_version": ANALYTICS_CONTRACT_VERSION,
        "generated_at": now.isoformat(),
        "definitions": {
            "universe": (
                "Canonical Research final-gate candidates, one candidate per fixture. "
                "Shared universe hard blocks, including blocked clubs, are excluded from "
                "active Research views and decisions. "
                "Retired OU_25 UNDER odds 1.40–1.80 and OU_25 OVER odds 1.61–1.80 "
                "remain visible in the entry-odds table but are excluded from active "
                "aggregate P/L, ROI, win rate and N."
            ),
            "roi": (
                "Flat P/L divided by fixed stake times graded WIN/LOSS count; "
                "voids are reported but excluded from the ROI denominator."
            ),
            "calibration_gap": "Observed win rate minus mean model probability, percentage points.",
            "clv": (
                "CLV is retained as a research metric and future validation axis. "
                "Current provider quote cadence is not used as a pruning gate; "
                "the plan is to cross-validate with an odds-specialized API."
            ),
            "decision_focus": (
                "ROI is the current north-star metric for the self-sustain phase; "
                "pruning must also respect sample size, uncertainty and temporal persistence."
            ),
            "versioning": (
                "Overall windows may combine versions; use model/policy/decision-contract "
                "cohorts for regime-specific conclusions. Legacy policy rows are never inferred."
            ),
            "sample_bands": {
                "COLLECT": "<100 graded",
                "WATCH": "100–249 graded",
                "SOFT_REVIEW": "250–499 graded",
                "DECISION_GRADE": "500–999 graded",
                "MATURE": "1000+ graded",
            },
        },
        "version_summary": _version_summary(settled_active),
        "windows": {
            "lifetime": cohort_metrics(settled_active, fixed_stake_minor=fixed_stake_minor),
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
            settled_active,
            fixed_stake_minor=fixed_stake_minor,
        ),
        "cohorts": {
            name: _cohort_rows(
                settled_all if name == "market_selection_odds" else settled_active,
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


def _metric_class(value: Any) -> str:
    if value is None:
        return "metric-neutral"
    number = float(value)
    if number > 0:
        return "metric-positive"
    if number < 0:
        return "metric-negative"
    return "metric-neutral"


def _roi_interval_class(low: Any, high: Any) -> str:
    if low is None or high is None:
        return "metric-neutral"
    if float(low) > 0:
        return "metric-positive"
    if float(high) < 0:
        return "metric-negative"
    return "metric-neutral"


def _bucket_sort_value(value: Any) -> float:
    text = str(value or "").strip().replace("%", "")
    if not text or text == "—":
        return float("-inf")
    if text.startswith("<"):
        try:
            return float(text[1:]) - 0.001
        except ValueError:
            return float("-inf")
    if text.endswith("+"):
        try:
            return float(text[:-1])
        except ValueError:
            return float("-inf")
    for separator in ("–", "-"):
        if separator in text:
            try:
                return float(text.split(separator, 1)[0])
            except ValueError:
                return float("-inf")
    try:
        return float(text)
    except ValueError:
        return float("-inf")


def _analytics_sort_value(row: dict[str, Any], key: str) -> Any:
    if key == "record":
        return (
            int(row.get("wins") or 0),
            -int(row.get("losses") or 0),
            -int(row.get("voids") or 0),
        )
    if key == "sample_band":
        return {
            "COLLECT": 0,
            "WATCH": 1,
            "SOFT_REVIEW": 2,
            "DECISION_GRADE": 3,
            "MATURE": 4,
        }.get(str(row.get(key) or ""), -1)
    if key in {
        "probability_bucket",
        "market_fair_probability_bucket",
        "ev_bucket",
        "edge_bucket",
        "odds_bucket",
    }:
        return _bucket_sort_value(row.get(key))
    if key == "time_to_kickoff_bucket":
        return {
            "after kickoff": -1,
            "<1h": 0,
            "1–3h": 1,
            "3–6h": 3,
            "6–12h": 6,
            "12–24h": 12,
            "24h+": 24,
        }.get(str(row.get(key) or ""), -2)
    if key in {"league_id", "season"}:
        try:
            return int(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value.casefold()
    return value


def _sorted_analytics_rows(
    rows: Sequence[dict[str, Any]],
    *,
    key: str,
    direction: str,
) -> list[dict[str, Any]]:
    if direction not in {"asc", "desc"}:
        direction = "desc"
    present: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for row in rows:
        value = _analytics_sort_value(row, key)
        if value is None:
            missing.append(row)
        else:
            present.append(row)
    present.sort(
        key=lambda row: _analytics_sort_value(row, key),
        reverse=direction == "desc",
    )
    return present + missing


def _sort_header(
    label: str,
    key: str,
    *,
    table_id: str,
    active_table: str,
    active_key: str,
    active_dir: str,
) -> str:
    def href(direction: str) -> str:
        query = urlencode(
            {
                "sort_table": table_id,
                "sort": key,
                "dir": direction,
            }
        )
        return f"/research/analytics?{query}#table-{table_id}"

    active_low = active_table == table_id and active_key == key and active_dir == "asc"
    active_high = active_table == table_id and active_key == key and active_dir == "desc"
    return (
        "<th><span class=\"th-wrap\"><span>"
        + escape(label)
        + "</span><span class=\"sort-tools\">"
        + f'<a class="{"sort-active" if active_low else ""}" '
        + f'href="{escape(href("asc"), quote=True)}" title="Lowest first">↑</a>'
        + f'<a class="{"sort-active" if active_high else ""}" '
        + f'href="{escape(href("desc"), quote=True)}" title="Highest first">↓</a>'
        + "</span></span></th>"
    )


def _metrics_table(
    title: str,
    rows: Sequence[dict[str, Any]],
    dimensions: tuple[str, ...],
    *,
    table_id: str,
    active_sort_table: str = "",
    active_sort_key: str = "",
    active_sort_dir: str = "desc",
    dimension_links: dict[str, str] | None = None,
    dimension_link_params: dict[str, tuple[str, ...]] | None = None,
    dimension_labels: dict[str, str] | None = None,
    row_link_path: str | None = None,
    row_link_params: dict[str, str] | None = None,
    row_link_fixed: dict[str, str] | None = None,
    compact_roi: bool = False,
) -> str:
    visible_rows = list(rows)
    if active_sort_table == table_id and active_sort_key:
        visible_rows = _sorted_analytics_rows(
            visible_rows,
            key=active_sort_key,
            direction=active_sort_dir,
        )

    dimension_headers = "".join(
        _sort_header(
            (dimension_labels or {}).get(name, name),
            name,
            table_id=table_id,
            active_table=active_sort_table,
            active_key=active_sort_key,
            active_dir=active_sort_dir,
        )
        for name in dimensions
    )
    metric_columns = (
        (
            ("N", "n"),
            ("W-L-V", "record"),
            ("ROI", "roi_pct"),
            ("Last 100", "roi_last_100_pct"),
            ("Last 250", "roi_last_250_pct"),
            ("Last 500", "roi_last_500_pct"),
            ("Avg odds", "avg_entry_odds"),
            ("Avg edge", "avg_edge_pct"),
            ("Evidence", "sample_band"),
        )
        if compact_roi
        else (
            ("N", "n"),
            ("W-L-V", "record"),
            ("Win%", "win_rate_pct"),
            ("Exp%", "expected_win_rate_pct"),
            ("Cal gap", "calibration_gap_pp"),
            ("ROI", "roi_pct"),
            ("Avg odds", "avg_entry_odds"),
            ("Avg edge", "avg_edge_pct"),
            ("Avg EV", "avg_ev_pct"),
            ("Avg CLV", "avg_clv_pct"),
            ("CLV n", "clv_count"),
            ("+CLV%", "positive_clv_rate_pct"),
            ("Evidence", "sample_band"),
        )
    )
    metric_headers = "".join(
        _sort_header(
            label,
            key,
            table_id=table_id,
            active_table=active_sort_table,
            active_key=active_sort_key,
            active_dir=active_sort_dir,
        )
        for label, key in metric_columns
    )
    action_header = "<th class=\"action-col\">Picks</th>" if row_link_path else ""
    body = []
    for row in visible_rows:
        row_href = None
        if row_link_path:
            query = dict(row_link_fixed or {})
            for row_name, query_name in (row_link_params or {}).items():
                query[query_name] = str(row.get(row_name, "—"))
            row_href = row_link_path + ("?" + urlencode(query) if query else "")

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
            elif row_href:
                cells.append(
                    f'<td><b><a class="dimension-link" href="{escape(row_href, quote=True)}">'
                    f"{value}</a></b></td>"
                )
            else:
                cells.append(f"<td><b>{value}</b></td>")
        dims = "".join(cells)
        action = (
            f'<td class="action-col"><a class="row-action" '
            f'href="{escape(row_href, quote=True)}">View →</a></td>'
            if row_href
            else ""
        )
        evidence = escape(str(row["sample_band"]))
        evidence_class = evidence.casefold().replace("_", "-")
        decision_ready = (
            compact_roi
            and int(row.get("graded_n") or 0) >= 500
            and row.get("roi_pct") is not None
            and float(row["roi_pct"]) > 0
            and row.get("roi_last_100_pct") is not None
            and float(row["roi_last_100_pct"]) > 0
            and row.get("roi_last_250_pct") is not None
            and float(row["roi_last_250_pct"]) > 0
            and row.get("roi_last_500_pct") is not None
            and float(row["roi_last_500_pct"]) > 0
        )
        if compact_roi:
            metric_cells = (
                f"<td>{row['n']}</td>"
                f"<td>{row['wins']}-{row['losses']}-{row['voids']}</td>"
                f'<td class="metric-strong {_metric_class(row["roi_pct"])}">'
                f"{_fmt(row['roi_pct'], '%', signed=True)}</td>"
                f'<td class="{_metric_class(row.get("roi_last_100_pct"))}">'
                f"{_fmt(row.get('roi_last_100_pct'), '%', signed=True)}</td>"
                f'<td class="{_metric_class(row.get("roi_last_250_pct"))}">'
                f"{_fmt(row.get('roi_last_250_pct'), '%', signed=True)}</td>"
                f'<td class="{_metric_class(row.get("roi_last_500_pct"))}">'
                f"{_fmt(row.get('roi_last_500_pct'), '%', signed=True)}</td>"
                f"<td>{_fmt(row.get('avg_entry_odds'))}</td>"
                f'<td class="{_metric_class(row.get("avg_edge_pct"))}">'
                f"{_fmt(row.get('avg_edge_pct'), '%', signed=True)}</td>"
                f'<td><span class="evidence evidence-{evidence_class}">{evidence}</span></td>'
            )
        else:
            metric_cells = (
                f"<td>{row['n']}</td>"
                f"<td>{row['wins']}-{row['losses']}-{row['voids']}</td>"
                f"<td>{_fmt(row['win_rate_pct'], '%')}</td>"
                f"<td>{_fmt(row['expected_win_rate_pct'], '%')}</td>"
                f'<td class="{_metric_class(row["calibration_gap_pp"])}">'
                f"{_fmt(row['calibration_gap_pp'], 'pp', signed=True)}</td>"
                f'<td class="metric-strong {_metric_class(row["roi_pct"])}">'
                f"{_fmt(row['roi_pct'], '%', signed=True)}</td>"
                f"<td>{_fmt(row.get('avg_entry_odds'))}</td>"
                f'<td class="{_metric_class(row.get("avg_edge_pct"))}">'
                f"{_fmt(row.get('avg_edge_pct'), '%', signed=True)}</td>"
                f'<td class="{_metric_class(row.get("avg_ev_pct"))}">'
                f"{_fmt(row.get('avg_ev_pct'), '%', signed=True)}</td>"
                f'<td class="{_metric_class(row.get("avg_clv_pct"))}">'
                f"{_fmt(row.get('avg_clv_pct'), '%', signed=True)}</td>"
                f"<td>{row.get('clv_count', 0)}</td>"
                f"<td>{_fmt(row.get('positive_clv_rate_pct'), '%')}</td>"
                f'<td><span class="evidence evidence-{evidence_class}">{evidence}</span></td>'
            )
        market = str(row.get("market") or "").upper()
        selection = str(row.get("selection") or "").upper()
        odds_bucket = str(row.get("odds_bucket") or "")
        retired_bucket = (
            market == "OU_25"
            and (
                (
                    selection == "UNDER"
                    and odds_bucket in {"1.40–1.60", "1.61–1.80"}
                )
                or (selection == "OVER" and odds_bucket == "1.61–1.80")
            )
        )
        row_classes = []
        if decision_ready:
            row_classes.append("bucket-qualified")
        if retired_bucket:
            row_classes.append("bucket-retired")
        row_class = " ".join(row_classes)
        if retired_bucket:
            row_title = (
                ' title="Retired from active Research and Production intake. '
                'Kept for visibility and historical tracking."'
            )
        elif decision_ready:
            row_title = (
                ' title="Decision-ready bucket: N ≥ 500, lifetime ROI > 0%, '
                'and Last 100/250/500 ROI all > 0%"'
            )
        else:
            row_title = ""
        body.append(
            f'<tr class="{row_class}"{row_title}>' + dims + metric_cells + action + "</tr>"
        )
    if not body:
        body.append(
            f'<tr><td colspan="{len(dimensions) + len(metric_columns) + (1 if row_link_path else 0)}" '
            'class="empty">No settled rows.</td></tr>'
        )
    return (
        f'<section id="table-{escape(table_id, quote=True)}" class="panel">'
        + '<div class="panel-title"><h3>'
        + escape(title)
        + '</h3><span class="row-count">'
        + str(len(visible_rows))
        + " buckets</span></div>"
        + '<div class="scroll"><table><thead><tr>'
        + dimension_headers
        + metric_headers
        + action_header
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div></section>"
    )


def _selected_research_production_buckets(
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve the four selected Research intake buckets to their current analytics rows."""
    specs = {
        spec.bucket_id: spec
        for spec in PRODUCTION_BUCKET_SPECS
        if spec.source_universe == "RESEARCH"
    }

    def find(rows: Sequence[dict[str, Any]], **expected: str) -> dict[str, Any] | None:
        for row in rows:
            if all(str(row.get(key) or "") == value for key, value in expected.items()):
                return row
        return None

    sources = (
        (
            RESEARCH_OU_UNDER_EDGE_10_15,
            find(
                snapshot["cohorts"]["market_selection_edge"],
                market="OU_25",
                selection="UNDER",
                edge_bucket="10–15%",
            ),
        ),
        (
            RESEARCH_OU_UNDER_EDGE_20_30,
            find(
                snapshot["cohorts"]["market_selection_edge"],
                market="OU_25",
                selection="UNDER",
                edge_bucket="20–30%",
            ),
        ),
        (
            RESEARCH_BTTS_NO_ODDS_2_01_2_50,
            find(
                snapshot["cohorts"]["market_selection_odds"],
                market="BTTS",
                selection="NO",
                odds_bucket="2.01–2.50",
            ),
        ),
        (
            RESEARCH_LOW_SCORING_NON_EXTREME,
            find(
                snapshot["diagnostics"],
                diagnostic="LOW_SCORING_NON_EXTREME",
            ),
        ),
    )

    output: list[dict[str, Any]] = []
    for bucket_id, metrics in sources:
        spec = specs[bucket_id]
        row = dict(metrics or {})
        graded_n = int(row.get("graded_n") or 0)
        roi_pct = row.get("roi_pct")
        row.update(
            {
                "bucket_id": bucket_id,
                "bucket_label": spec.label,
                "analytics_path": spec.analytics_path,
                "priority_score": n_roi_priority_score(
                    graded_n=graded_n,
                    roi_pct=None if roi_pct is None else float(roi_pct),
                ),
            }
        )
        output.append(row)
    return sorted(
        output,
        key=lambda item: (
            float(item["priority_score"]),
            float(item.get("roi_pct") or float("-inf")),
            int(item.get("graded_n") or 0),
        ),
        reverse=True,
    )


def _selected_research_bucket_table(snapshot: dict[str, Any]) -> str:
    rows = _selected_research_production_buckets(snapshot)
    rendered = []
    for priority, row in enumerate(rows, 1):
        href = str(row["analytics_path"])
        n = int(row.get("graded_n") or 0)
        wins = int(row.get("wins") or 0)
        losses = int(row.get("losses") or 0)
        voids = int(row.get("voids") or 0)
        evidence = escape(str(row.get("sample_band") or "—"))
        rendered.append(
            '<tr class="production-bucket-row">'
            f'<td><span class="priority-rank">#{priority}</span></td>'
            f'<td><a class="production-bucket-link" href="{escape(href, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">'
            f'{escape(str(row["bucket_label"]))}</a>'
            f'<small><code>{escape(str(row["bucket_id"]))}</code></small></td>'
            f'<td>{n}</td><td>{wins}-{losses}-{voids}</td>'
            f'<td class="metric-strong {_metric_class(row.get("roi_pct"))}">'
            f'{_fmt(row.get("roi_pct"), "%", signed=True)}</td>'
            f'<td>{_fmt(row.get("priority_score"))}</td>'
            f'<td>{_fmt(row.get("avg_entry_odds"))}</td>'
            f'<td class="{_metric_class(row.get("avg_edge_pct"))}">'
            f'{_fmt(row.get("avg_edge_pct"), "%", signed=True)}</td>'
            f'<td><span class="evidence">{evidence}</span></td>'
            "</tr>"
        )
    return (
        '<section class="panel production-intake-panel" id="production-intake-buckets">'
        '<div class="panel-title"><h3>Production intake · selected buckets</h3>'
        '<span class="row-count">neon blue = approved intake · priority = ROI × min(graded N / 100, 1)</span></div>'
        '<div class="scroll"><table><thead><tr>'
        '<th>Priority</th><th>Bucket</th><th>Graded N</th><th>W-L-V</th><th>Current ROI</th>'
        '<th>N+ROI score</th><th>Avg odds</th><th>Avg edge</th><th>Evidence</th>'
        '</tr></thead><tbody>'
        + "".join(rendered)
        + "</tbody></table></div></section>"
    )


def render_research_analytics_html(snapshot: dict[str, Any], query: str = "") -> str:
    params = parse_qs(query, keep_blank_values=True)
    active_sort_table = params.get("sort_table", [""])[0].strip()
    active_sort_key = params.get("sort", [""])[0].strip()
    active_sort_dir = params.get("dir", ["desc"])[0].strip().casefold()
    if active_sort_dir not in {"asc", "desc"}:
        active_sort_dir = "desc"

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
        'Decision tables aggregate regimes; Audit preserves version detail.</span></div>'
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
            ("ROI", _fmt(lifetime["roi_pct"], "%", signed=True)),
            ("Win rate", _fmt(lifetime["win_rate_pct"], "%")),
            ("Expected", _fmt(lifetime["expected_win_rate_pct"], "%")),
            ("Calibration", _fmt(lifetime["calibration_gap_pp"], "pp", signed=True)),
            ("Avg CLV*", _fmt(lifetime["avg_clv_pct"], "%", signed=True)),
            ("CLV coverage", _fmt(lifetime["clv_coverage_pct"], "%")),
        )
    )

    history = {"tab": "history"}

    league_seasons = _metrics_table(
        "Leagues · all retrains combined",
        snapshot["cohorts"]["league_season"],
        ("competition_name", "league_id", "season"),
        table_id="leagues",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_links={"competition_name": "/research/analytics/league"},
        dimension_link_params={"competition_name": ("league_id", "season")},
        dimension_labels={
            "competition_name": "League",
            "league_id": "League ID",
            "season": "Season",
        },
        row_link_path="/research/analytics/league",
        row_link_params={"league_id": "league_id", "season": "season"},
        compact_roi=True,
    )
    market_selection = _metrics_table(
        "Market × selection",
        snapshot["cohorts"]["market_selection"],
        ("market", "selection"),
        table_id="markets",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"market": "Market", "selection": "Pick"},
        row_link_path="/research",
        row_link_params={"market": "market", "selection": "selection"},
        row_link_fixed=history,
        compact_roi=True,
    )
    market_selection_odds = _metrics_table(
        "Market × selection × entry odds",
        snapshot["cohorts"]["market_selection_odds"],
        ("market", "selection", "odds_bucket"),
        table_id="market-odds",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"market": "Market", "selection": "Pick", "odds_bucket": "Odds"},
        row_link_path="/research",
        row_link_params={
            "market": "market",
            "selection": "selection",
            "odds_bucket": "odds_bucket",
        },
        row_link_fixed=history,
        compact_roi=True,
    )
    market_selection_edge = _metrics_table(
        "Market × selection × edge",
        snapshot["cohorts"]["market_selection_edge"],
        ("market", "selection", "edge_bucket"),
        table_id="market-edge",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"market": "Market", "selection": "Pick", "edge_bucket": "Edge"},
        row_link_path="/research",
        row_link_params={
            "market": "market",
            "selection": "selection",
            "edge_bucket": "edge_bucket",
        },
        row_link_fixed=history,
        compact_roi=True,
    )
    league_market = _metrics_table(
        "League × market × selection",
        snapshot["cohorts"]["league_market"],
        ("competition_name", "league_id", "market", "selection"),
        table_id="league-market",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={
            "competition_name": "League",
            "league_id": "League ID",
            "market": "Market",
            "selection": "Pick",
        },
        row_link_path="/research",
        row_link_params={
            "competition_name": "league",
            "league_id": "league_id",
            "market": "market",
            "selection": "selection",
        },
        row_link_fixed=history,
        compact_roi=True,
    )
    edge = _metrics_table(
        "Edge buckets",
        snapshot["cohorts"]["edge_bucket"],
        ("edge_bucket",),
        table_id="edge",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"edge_bucket": "Edge"},
        row_link_path="/research",
        row_link_params={"edge_bucket": "edge_bucket"},
        row_link_fixed=history,
        compact_roi=True,
    )
    odds = _metrics_table(
        "Entry odds",
        snapshot["cohorts"]["odds_bucket"],
        ("odds_bucket",),
        table_id="odds",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"odds_bucket": "Odds"},
        row_link_path="/research",
        row_link_params={"odds_bucket": "odds_bucket"},
        row_link_fixed=history,
        compact_roi=True,
    )
    time_to_kickoff = _metrics_table(
        "Time to kickoff",
        snapshot["cohorts"]["time_to_kickoff_bucket"],
        ("time_to_kickoff_bucket",),
        table_id="ttk",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"time_to_kickoff_bucket": "TTK"},
        row_link_path="/research",
        row_link_params={"time_to_kickoff_bucket": "ttk_bucket"},
        row_link_fixed=history,
        compact_roi=True,
    )
    weekly = _metrics_table(
        "Weekly stability",
        snapshot["weekly"],
        ("week",),
        table_id="weekly",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"week": "Week"},
        row_link_path="/research",
        row_link_params={"week": "week"},
        row_link_fixed=history,
        compact_roi=True,
    )

    model_probability = _metrics_table(
        "Model probability",
        snapshot["cohorts"]["model_probability_bucket"],
        ("probability_bucket",),
        table_id="model-p",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"probability_bucket": "Model P"},
        row_link_path="/research",
        row_link_params={"probability_bucket": "p_bucket"},
        row_link_fixed=history,
    )
    fair_probability = _metrics_table(
        "Market fair probability",
        snapshot["cohorts"]["market_fair_probability_bucket"],
        ("market_fair_probability_bucket",),
        table_id="fair-p",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"market_fair_probability_bucket": "Fair P"},
        row_link_path="/research",
        row_link_params={"market_fair_probability_bucket": "fair_bucket"},
        row_link_fixed=history,
    )
    ev = _metrics_table(
        "Expected value",
        snapshot["cohorts"]["ev_bucket"],
        ("ev_bucket",),
        table_id="ev",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"ev_bucket": "EV"},
        row_link_path="/research",
        row_link_params={"ev_bucket": "ev_bucket"},
        row_link_fixed=history,
    )
    production_intake = _selected_research_bucket_table(snapshot)
    diagnostics = _metrics_table(
        "Low-scoring diagnostic",
        snapshot["diagnostics"],
        ("diagnostic",),
        table_id="diagnostics",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"diagnostic": "Diagnostic"},
        row_link_path="/research",
        row_link_params={"diagnostic": "diagnostic"},
        row_link_fixed=history,
    )

    policy_configs = _metrics_table(
        "Policy configurations",
        snapshot["cohorts"]["policy_config"],
        ("policy_config_fingerprint",),
        table_id="policy",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_labels={"policy_config_fingerprint": "Policy"},
        row_link_path="/research",
        row_link_params={"policy_config_fingerprint": "policy_config"},
        row_link_fixed=history,
    )
    model_policy = _metrics_table(
        "Model × policy",
        snapshot["cohorts"]["model_policy"],
        ("model_version_id", "policy_config_fingerprint"),
        table_id="model-policy",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_links={"model_version_id": "/research/analytics/model"},
        dimension_labels={
            "model_version_id": "Model version",
            "policy_config_fingerprint": "Policy",
        },
        row_link_path="/research",
        row_link_params={
            "model_version_id": "model_version",
            "policy_config_fingerprint": "policy_config",
        },
        row_link_fixed=history,
    )
    decision_contract = _metrics_table(
        "Decision contract",
        snapshot["cohorts"]["decision_contract"],
        (
            "model_version_id",
            "prediction_method_version",
            "devig_method_version",
            "policy_config_fingerprint",
        ),
        table_id="decision-contract",
        active_sort_table=active_sort_table,
        active_sort_key=active_sort_key,
        active_sort_dir=active_sort_dir,
        dimension_links={"model_version_id": "/research/analytics/model"},
        dimension_labels={
            "model_version_id": "Model version",
            "prediction_method_version": "Prediction",
            "devig_method_version": "De-vig",
            "policy_config_fingerprint": "Policy",
        },
        row_link_path="/research",
        row_link_params={
            "model_version_id": "model_version",
            "prediction_method_version": "prediction_method",
            "devig_method_version": "devig_method",
            "policy_config_fingerprint": "policy_config",
        },
        row_link_fixed=history,
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantBet Research Analytics V2</title>
<style>
:root{{--bg:#0f1113;--panel:#171a1e;--panel2:#13161a;--line:#2b3138;--text:#f0f2f4;
--muted:#8e979f;--positive:#7bc69a;--negative:#e27b82;--accent:#c9a861;--soft:#20252b}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);
color:var(--text);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
main{{max-width:1920px;margin:auto;padding:24px}}
header{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:14px}}
h1{{margin:0;font-size:26px;letter-spacing:-.02em}}h2{{font-size:19px;margin:0}}h3{{font-size:15px;margin:0}}
p,small{{color:var(--muted)}}a{{color:#dce1e5}}
.section-nav{{position:sticky;top:0;z-index:30;display:flex;gap:8px;overflow:auto;
padding:10px 0;background:rgba(15,17,19,.96);border-bottom:1px solid #23282d;backdrop-filter:blur(10px)}}
.section-nav a{{text-decoration:none;white-space:nowrap;padding:7px 11px;border:1px solid var(--line);
border-radius:999px;font-size:12px;color:#bdc5cb}}.section-nav a:hover{{color:#fff;border-color:#646d75}}
.focus-note{{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-top:12px;
padding:12px 14px;border:1px solid #4b4330;border-radius:12px;background:#1f1b14}}
.focus-note b{{color:#e4c57f;font-size:12px;letter-spacing:.05em}}.focus-note span{{color:var(--muted);font-size:12px}}
.definition{{margin-top:10px;padding:11px 13px;border:1px solid var(--line);border-radius:10px;
color:var(--muted);font-size:12px;background:var(--panel2);line-height:1.55}}
.dimension-link{{text-decoration:none;border-bottom:1px dotted #778089}}
.dimension-link:hover{{color:#fff;border-bottom-color:#fff}}.row-action{{font-weight:700;
text-decoration:none;white-space:nowrap}}.cards{{display:grid;
grid-template-columns:repeat(8,minmax(120px,1fr));gap:9px;margin:14px 0 18px}}
.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:14px}}
.card{{padding:14px;min-height:78px}}.card small{{text-transform:uppercase;font-size:10px;letter-spacing:.09em}}
.card b{{display:block;font-size:20px;margin-top:7px;letter-spacing:-.02em}}.analytics-group{{scroll-margin-top:62px;
margin:22px 0 30px}}.group-head{{display:flex;align-items:end;justify-content:space-between;
gap:12px;padding:0 2px 8px}}.group-head p{{margin:3px 0 0;font-size:12px}}
.panel{{padding:0;margin:11px 0;overflow:hidden}}.panel-title{{display:flex;justify-content:space-between;
align-items:center;padding:13px 14px;border-bottom:1px solid #252b31}}.row-count{{font-size:11px;color:var(--muted)}}
.scroll{{overflow:auto;max-height:66vh}}table{{width:100%;border-collapse:separate;border-spacing:0;font-size:12px}}
th,td{{padding:9px 10px;border-bottom:1px solid #252a30;white-space:nowrap;text-align:left}}
th{{position:sticky;top:0;z-index:4;background:#1c2025;color:#9da5ad;font-size:10px;text-transform:uppercase;letter-spacing:.055em}}
th:first-child,td:first-child{{position:sticky;left:0;z-index:3;background:var(--panel)}}
th:first-child{{z-index:5;background:#1c2025}}tbody tr:nth-child(even) td{{background:#181c20}}
tbody tr:nth-child(even) td:first-child{{background:#181c20}}tbody tr:hover td{{background:#20262b}}
tbody tr:hover td:first-child{{background:#20262b}}.th-wrap{{display:flex;align-items:center;gap:6px}}
.sort-tools{{display:inline-flex;gap:2px}}.sort-tools a{{display:inline-grid;place-items:center;width:17px;height:17px;
border:1px solid #343b42;border-radius:4px;text-decoration:none;color:#737b83;font-size:10px;line-height:1}}
.sort-tools a:hover,.sort-tools a.sort-active{{color:#fff;border-color:#778089;background:#252b30}}
.action-col{{text-align:right}}.metric-strong{{font-weight:800;font-size:12.5px}}
.metric-positive{{color:var(--positive)}}.metric-negative{{color:var(--negative)}}.metric-neutral{{color:inherit}}
tbody tr.bucket-qualified td{{background:#16251c;box-shadow:inset 0 1px 0 #315b3f,inset 0 -1px 0 #315b3f}}
tbody tr.bucket-qualified td:first-child{{background:#16251c;box-shadow:inset 3px 0 0 #79c995,inset 0 1px 0 #315b3f,inset 0 -1px 0 #315b3f}}
tbody tr.bucket-qualified:hover td,tbody tr.bucket-qualified:hover td:first-child{{background:#1a2d22}}
tbody tr.bucket-retired td{{box-shadow:inset 0 1px 0 #8b2d2d,inset 0 -1px 0 #8b2d2d}}
tbody tr.bucket-retired td:first-child{{box-shadow:inset 3px 0 0 #d05a5a,inset 0 1px 0 #8b2d2d,inset 0 -1px 0 #8b2d2d}}
tbody tr.bucket-retired td:last-child{{box-shadow:inset -1px 0 0 #8b2d2d,inset 0 1px 0 #8b2d2d,inset 0 -1px 0 #8b2d2d}}
tbody tr.bucket-retired:hover td{{background:#2a1818}}
.production-intake-panel{{border:2px solid #18d7ff;box-shadow:0 0 18px rgba(24,215,255,.24),inset 0 0 0 1px rgba(24,215,255,.12);background:linear-gradient(180deg,rgba(24,215,255,.055),var(--panel))}}
.production-intake-panel .panel-title{{border-bottom-color:#168fb0;background:rgba(24,215,255,.045)}}
.production-intake-panel .panel-title h3{{color:#7eeaff;text-transform:uppercase;letter-spacing:.08em}}
.production-bucket-row td{{box-shadow:inset 0 1px 0 rgba(24,215,255,.34),inset 0 -1px 0 rgba(24,215,255,.34);background:rgba(10,63,76,.18)}}
.production-bucket-row td:first-child{{box-shadow:inset 3px 0 0 #18d7ff,inset 0 1px 0 rgba(24,215,255,.34),inset 0 -1px 0 rgba(24,215,255,.34)}}
.production-bucket-link{{color:#7eeaff;font-weight:900;text-decoration:none;border-bottom:1px solid rgba(126,234,255,.6)}}
.production-bucket-link:hover{{color:#d7f9ff;border-bottom-color:#d7f9ff}}
.priority-rank{{display:inline-flex;min-width:26px;justify-content:center;padding:3px 6px;border:1px solid #18d7ff;border-radius:999px;color:#7eeaff;font-weight:900}}
.empty{{color:var(--muted);text-align:center}}.evidence{{display:inline-flex;padding:3px 7px;border-radius:999px;
font-size:9px;font-weight:800;letter-spacing:.055em;border:1px solid #3a4148;color:#b5bdc4;background:#20252b}}
.evidence-decision-grade,.evidence-mature{{border-color:#496b58;color:#9fd0af;background:#17231c}}
.evidence-soft-review{{border-color:#6e5e3d;color:#d7bd83;background:#241f16}}
.version-warning,.version-ok{{display:flex;gap:10px;align-items:center;padding:11px 14px;margin:12px 0;
border-radius:10px;border:1px solid var(--line);font-size:12px}}.version-warning{{background:#2a2117}}
.version-warning b{{color:#f0b36a}}.version-ok{{background:#17251d}}.version-ok b{{color:#79c995}}
.version-warning span,.version-ok span{{color:var(--muted)}}.audit-details{{border:1px solid var(--line);
border-radius:12px;background:var(--panel2);margin:10px 0;padding:0 12px 12px}}
.audit-details summary{{cursor:pointer;padding:12px 2px;color:#c9d0d5;font-weight:700;font-size:13px}}
.legend{{margin:34px 0 8px;padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--panel2)}}
.legend h2{{margin:0 0 12px;font-size:16px}}.legend-grid{{display:grid;
grid-template-columns:repeat(2,minmax(280px,1fr));gap:10px 18px}}.legend-item{{padding:10px 0;
border-bottom:1px solid #242a30;font-size:12px;line-height:1.55;color:var(--muted)}}
.legend-item b{{display:block;color:#dce1e5;margin-bottom:2px}}.legend-note{{margin:12px 0 0;
font-size:11px;color:#7f8992;line-height:1.5}}
@media(max-width:1100px){{.cards{{grid-template-columns:repeat(4,1fr)}}}}
@media(max-width:760px){{.cards{{grid-template-columns:repeat(2,1fr)}}main{{padding:14px}}header{{display:block}}
.group-head{{display:block}}.group-head p{{margin-top:4px}}table{{font-size:11px}}.focus-note{{display:block}}
.focus-note span{{display:block;margin-top:5px}}.legend-grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<header><div><small>{ANALYTICS_CONTRACT_VERSION}</small><h1>Research Analytics V2</h1>
<p>ROI-first evidence dashboard. Every aggregate row drills into its constituent picks.</p></div>
<div><a href="/research">← Research Board</a> ·
<a href="/research/analytics.json">JSON</a></div></header>
<nav class="section-nav">
<a href="#overview">Overview</a><a href="#decision">ROI decision lab</a>
<a href="#calibration">Calibration & CLV</a><a href="#audit">Audit</a>
</nav>
<section id="overview" class="analytics-group">
<div class="focus-note"><b>ROI-FIRST SELF-SUSTAIN PHASE</b>
<span>CLV stays in the model roadmap, but current pruning is driven by ROI + N + uncertainty + persistence.</span></div>
<div class="definition">Universe: {escape(snapshot['definitions']['universe'])}<br>
ROI: {escape(snapshot['definitions']['roi'])}<br>
Decision focus: {escape(snapshot['definitions']['decision_focus'])}<br>
CLV*: {escape(snapshot['definitions']['clv'])}<br>
Versioning: {escape(snapshot['definitions']['versioning'])}</div>
{version_notice}
<section class="cards">{cards}</section>
</section>
<section id="decision" class="analytics-group">
<div class="group-head"><div><h2>ROI decision lab</h2>
<p>Low-dimensional buckets first. Rolling 100/250/500 only appears after that bucket has enough graded picks.</p></div></div>
{production_intake}{market_selection}{market_selection_odds}{market_selection_edge}{edge}{odds}{time_to_kickoff}{league_market}{league_seasons}{weekly}
</section>
<section id="calibration" class="analytics-group">
<div class="group-head"><div><h2>Calibration & CLV</h2>
<p>Model confidence, market price and CLV remain research axes; CLV is not a current pruning gate.</p></div></div>
{model_probability}{fair_probability}{ev}
</section>
<section id="audit" class="analytics-group">
<div class="group-head"><div><h2>Audit</h2>
<p>Version provenance and hypothesis diagnostics are preserved without crowding the decision surface.</p></div></div>
<details class="audit-details"><summary>Research diagnostics</summary>{diagnostics}</details>
<details class="audit-details"><summary>Version / policy cohorts</summary>{policy_configs}{model_policy}{decision_contract}</details>
</section>

<section id="legend" class="legend">
<h2>Legend · how to read Analytics</h2>
<div class="legend-grid">
<div class="legend-item"><b>ROI</b>Realized flat-stake return on graded WIN/LOSS picks. Positive is profit; negative is loss.</div>
<div class="legend-item"><b>Last 100 / 250 / 500</b>ROI from the most recent 100, 250 or 500 graded picks inside that exact bucket. A value appears only after the bucket has at least that many graded picks.</div>
<div class="legend-item"><b>N / W-L-V</b>Settled sample size and Win-Loss-Void record. Voids are shown but excluded from the ROI denominator.</div>
<div class="legend-item"><b>Avg odds</b>Average entry odds of the picks in that bucket.</div>
<div class="legend-item"><b>Avg edge</b>Average model edge recorded at decision time. It is a model signal, not proof of realized profitability.</div>
<div class="legend-item"><b>Evidence</b>Sample maturity: COLLECT &lt;100, WATCH 100–249, SOFT_REVIEW 250–499, DECISION_GRADE 500–999, MATURE 1000+ graded picks.</div>
<div class="legend-item"><b>Green bucket</b>A bucket turns green only when N ≥ 500, lifetime ROI is positive, and Last 100 / 250 / 500 ROI are all positive. Green means persistent positive performance across the full sample and recent windows, not automatic production activation.</div>
<div class="legend-item"><b>Red outline</b>Retired Research segments: OU_25 UNDER odds 1.40–1.60 and 1.61–1.80, plus OU_25 OVER odds 1.61–1.80. They remain visible for historical tracking but are excluded from active Research decisions and Production intake.</div>
<div class="legend-item"><b>CLV*</b>Retained for research and future odds-API validation. Current CLV is not used as a pruning gate because the present odds feed is not a reliable true-closing feed.</div>
</div>
<p class="legend-note">Important: no single column automatically means KEEP or BAN. QuantBet pruning should use ROI together with sample size, uncertainty, recent-window persistence and out-of-sample confirmation.</p>
</section>
</main></body></html>"""
