"""Read-only operational audit for CornerLab V2.

This module never writes to the database. It summarizes the append-only decision ledger,
model artifacts, feature snapshots, market/value coverage, and settled pre-match model
performance so Railway operators can diagnose zero-pick states without guessing.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from math import lgamma, log, sqrt
from statistics import fmean, variance
from typing import Any


POLICY_VERSION = "CORNERLAB_PRESSURE_POISSON_POLICY_V2"


def _rows(cursor: Any) -> tuple[dict[str, Any], ...]:
    columns = tuple(item.name for item in cursor.description)
    return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


def _one(cursor: Any) -> dict[str, Any]:
    rows = _rows(cursor)
    return {} if not rows else rows[0]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rounded(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def quantile(p: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        pos = (len(ordered) - 1) * p
        low = int(pos)
        high = min(low + 1, len(ordered) - 1)
        weight = pos - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight

    return {
        "n": len(ordered),
        "min": _rounded(ordered[0]),
        "p05": _rounded(quantile(0.05)),
        "p25": _rounded(quantile(0.25)),
        "median": _rounded(quantile(0.50)),
        "mean": _rounded(fmean(ordered)),
        "p75": _rounded(quantile(0.75)),
        "p95": _rounded(quantile(0.95)),
        "max": _rounded(ordered[-1]),
    }


def _quality(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    pairs: list[tuple[float, float, str]] = []
    for row in rows:
        actual = _number(row.get("actual_total_corners"))
        predicted = _number(row.get("expected_total_corners"))
        if actual is None or predicted is None or predicted <= 0:
            continue
        pairs.append((actual, predicted, str(row.get("competition_name") or "UNKNOWN")))

    if not pairs:
        return {"n": 0, "sufficient_for_quality_audit": False}

    actuals = [item[0] for item in pairs]
    predicted = [item[1] for item in pairs]
    residuals = [actual - mu for actual, mu, _ in pairs]
    mae = fmean(abs(item) for item in residuals)
    rmse = sqrt(fmean(item * item for item in residuals))
    poisson_ll = sum(
        actual * log(mu) - mu - lgamma(actual + 1.0)
        for actual, mu, _ in pairs
    )
    observed_mean = fmean(actuals)
    observed_variance = variance(actuals) if len(actuals) > 1 else 0.0
    residual_variance = variance(residuals) if len(residuals) > 1 else 0.0

    by_league: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for actual, mu, league in pairs:
        by_league[league].append((actual, mu))

    league_rows: list[dict[str, Any]] = []
    for league, items in by_league.items():
        if len(items) < 10:
            continue
        league_actual = [item[0] for item in items]
        league_pred = [item[1] for item in items]
        league_resid = [a - p for a, p in items]
        league_rows.append(
            {
                "league": league,
                "n": len(items),
                "observed_mean": _rounded(fmean(league_actual)),
                "predicted_mean": _rounded(fmean(league_pred)),
                "mae": _rounded(fmean(abs(item) for item in league_resid)),
                "rmse": _rounded(sqrt(fmean(item * item for item in league_resid))),
                "variance_to_mean": _rounded(
                    (variance(league_actual) / fmean(league_actual))
                    if len(league_actual) > 1 and fmean(league_actual) > 0
                    else None
                ),
            }
        )
    league_rows.sort(key=lambda item: (-int(item["n"]), str(item["league"])))

    return {
        "n": len(pairs),
        "sufficient_for_quality_audit": len(pairs) >= 30,
        "observed_mean": _rounded(observed_mean),
        "predicted_mean": _rounded(fmean(predicted)),
        "mae": _rounded(mae),
        "rmse": _rounded(rmse),
        "residual_variance": _rounded(residual_variance),
        "observed_variance": _rounded(observed_variance),
        "variance_to_mean": _rounded(
            observed_variance / observed_mean if observed_mean > 0 else None
        ),
        "poisson_log_likelihood": _rounded(poisson_ll),
        "poisson_mean_log_likelihood": _rounded(poisson_ll / len(pairs)),
        "league_split_n_ge_10": league_rows[:25],
    }


def _calibration(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        probability = _number(row.get("model_probability"))
        line = _number(row.get("line"))
        total = _number(row.get("actual_total_corners"))
        if probability is None or line is None or total is None:
            continue
        if not 0 < probability < 1:
            continue
        outcome = 1.0 if total > line else 0.0
        samples.append(
            {
                "fixture_id": str(row.get("fixture_id") or "UNKNOWN"),
                "p": probability,
                "y": outcome,
                "line": line,
                "bookmaker_name": str(row.get("bookmaker_name") or "UNKNOWN"),
                "competition_name": str(row.get("competition_name") or "UNKNOWN"),
            }
        )

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"n": 0}
        brier = fmean((item["p"] - item["y"]) ** 2 for item in items)
        log_loss = -fmean(
            item["y"] * log(item["p"])
            + (1.0 - item["y"]) * log(1.0 - item["p"])
            for item in items
        )
        return {
            "n": len(items),
            "mean_model_probability": _rounded(fmean(item["p"] for item in items)),
            "observed_over_rate": _rounded(fmean(item["y"] for item in items)),
            "brier": _rounded(brier),
            "log_loss": _rounded(log_loss),
        }

    canonical: dict[tuple[str, float], dict[str, Any]] = {}
    by_book: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in samples:
        canonical.setdefault((item["fixture_id"], item["line"]), item)
        by_book[item["bookmaker_name"]].append(item)

    canonical_samples = list(canonical.values())
    by_line: dict[float, list[dict[str, Any]]] = defaultdict(list)
    by_league: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_bin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in canonical_samples:
        by_line[item["line"]].append(item)
        by_league[item["competition_name"]].append(item)
        low = min(9, max(0, int(item["p"] * 10)))
        key = f"{low / 10:.1f}-{(low + 1) / 10:.1f}"
        by_bin[key].append(item)

    def grouped(
        source: dict[Any, list[dict[str, Any]]],
        label: str,
        minimum: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        result = []
        for key, items in source.items():
            if len(items) < minimum:
                continue
            result.append({label: key, **summarize(items)})
        result.sort(key=lambda item: (-int(item["n"]), str(item[label])))
        return result[:limit]

    return {
        "over_only_note": (
            "UNDER is the exact complement on half-lines; its Brier/log-loss is "
            "mathematically identical to the OVER representation used here."
        ),
        "canonical_note": (
            "Overall/line/league/bin calibration uses one model probability per "
            "fixture+line; bookmaker split keeps one row per bookmaker."
        ),
        "overall": summarize(canonical_samples),
        "line_split_n_ge_10": grouped(by_line, "line", 10, 30),
        "bookmaker_split_n_ge_10": grouped(by_book, "bookmaker", 10, 10),
        "league_split_n_ge_10": grouped(by_league, "league", 10, 25),
        "probability_bins_n_ge_5": grouped(by_bin, "probability_bin", 5, 10),
    }


def collect_cornerlab_v2_audit(repository: Any) -> dict[str, Any]:
    """Collect exact read-only CornerLab V2 diagnostics from PostgreSQL."""
    with repository.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT decision, reason, COUNT(*)::BIGINT AS row_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s "
            "GROUP BY decision, reason "
            "ORDER BY row_count DESC, decision, reason",
            (POLICY_VERSION,),
        )
        reasons = _rows(cursor)

        cursor.execute(
            "SELECT COUNT(*)::BIGINT AS model_count, "
            "MIN(training_sample_size)::BIGINT AS min_training_sample_size, "
            "MAX(training_sample_size)::BIGINT AS max_training_sample_size, "
            "MIN(history_match_count)::BIGINT AS min_history_match_count, "
            "MAX(history_match_count)::BIGINT AS max_history_match_count, "
            "MAX(trained_at) AS latest_trained_at "
            "FROM quantlab_corner_model_versions"
        )
        model_summary = _one(cursor)

        cursor.execute(
            "SELECT model_version, trained_at, training_cutoff, "
            "training_sample_size, history_match_count, ridge_penalty "
            "FROM quantlab_corner_model_versions "
            "ORDER BY trained_at DESC, model_version DESC LIMIT 12"
        )
        latest_models = _rows(cursor)

        cursor.execute(
            "SELECT COUNT(*)::BIGINT AS snapshot_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count, "
            "COUNT(*) FILTER (WHERE home_history_size >= 3 AND away_history_size >= 3)::BIGINT "
            "AS rows_both_history_ge_3, "
            "COUNT(DISTINCT fixture_id) FILTER "
            "(WHERE home_history_size >= 3 AND away_history_size >= 3)::BIGINT "
            "AS fixtures_both_history_ge_3, "
            "MIN(expected_total_corners) AS expected_min, "
            "percentile_cont(0.05) WITHIN GROUP (ORDER BY expected_total_corners) AS expected_p05, "
            "percentile_cont(0.25) WITHIN GROUP (ORDER BY expected_total_corners) AS expected_p25, "
            "percentile_cont(0.50) WITHIN GROUP (ORDER BY expected_total_corners) AS expected_median, "
            "AVG(expected_total_corners) AS expected_mean, "
            "percentile_cont(0.75) WITHIN GROUP (ORDER BY expected_total_corners) AS expected_p75, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY expected_total_corners) AS expected_p95, "
            "MAX(expected_total_corners) AS expected_max, "
            "STDDEV_SAMP(expected_total_corners) AS expected_stddev, "
            "MIN(home_history_size)::BIGINT AS home_history_min, "
            "percentile_cont(0.50) WITHIN GROUP (ORDER BY home_history_size) AS home_history_median, "
            "AVG(home_history_size) AS home_history_mean, "
            "MAX(home_history_size)::BIGINT AS home_history_max, "
            "MIN(away_history_size)::BIGINT AS away_history_min, "
            "percentile_cont(0.50) WITHIN GROUP (ORDER BY away_history_size) AS away_history_median, "
            "AVG(away_history_size) AS away_history_mean, "
            "MAX(away_history_size)::BIGINT AS away_history_max "
            "FROM quantlab_corner_feature_snapshots"
        )
        snapshots = _one(cursor)

        cursor.execute(
            "WITH fixture_meta AS ("
            " SELECT f.fixture_id, COALESCE(q.kickoff_at, p.kickoff_at) AS kickoff_at "
            " FROM quantlab_fixtures f "
            " LEFT JOIN LATERAL ("
            "  SELECT kickoff_at FROM quantlab_fixture_observations o "
            "  WHERE o.fixture_id = f.fixture_id "
            "  ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
            " ) q ON TRUE "
            " LEFT JOIN LATERAL ("
            "  SELECT kickoff_at FROM fixture_observations o "
            "  WHERE o.fixture_id = f.fixture_id "
            "  ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
            " ) p ON TRUE"
            "), policy_fixtures AS ("
            " SELECT DISTINCT fixture_id FROM quantlab_context_market_decisions "
            " WHERE policy_version = %s"
            ") "
            "SELECT "
            "(SELECT COUNT(*)::BIGINT FROM policy_fixtures) AS policy_fixture_count, "
            "COUNT(*) FILTER (WHERE fm.kickoff_at > CURRENT_TIMESTAMP)::BIGINT "
            "AS upcoming_policy_fixtures, "
            "COUNT(*) FILTER (WHERE fm.kickoff_at > CURRENT_TIMESTAMP AND EXISTS ("
            " SELECT 1 FROM quantlab_corner_feature_snapshots s "
            " WHERE s.fixture_id = pf.fixture_id "
            " AND s.home_history_size >= 3 AND s.away_history_size >= 3"
            "))::BIGINT AS upcoming_with_sufficient_team_history, "
            "(SELECT COUNT(DISTINCT fixture_id)::BIGINT "
            " FROM quantlab_context_market_decisions "
            " WHERE policy_version = %s AND reason = 'NO_SUPPORTED_TOTAL_MARKET') "
            "AS fixtures_no_supported_total_market, "
            "(SELECT COUNT(DISTINCT fixture_id)::BIGINT "
            " FROM quantlab_context_market_decisions "
            " WHERE policy_version = %s AND provider_bet_id IS NOT NULL AND line IS NOT NULL) "
            "AS fixtures_with_evaluated_total_market, "
            "(SELECT COUNT(DISTINCT (fixture_id, provider_bet_id, line))::BIGINT "
            " FROM quantlab_context_market_decisions "
            " WHERE policy_version = %s AND provider_bet_id IS NOT NULL AND line IS NOT NULL) "
            "AS canonical_fixture_market_lines, "
            "(SELECT COUNT(DISTINCT (fixture_id, bookmaker_id, provider_bet_id, line))::BIGINT "
            " FROM quantlab_context_market_decisions "
            " WHERE policy_version = %s AND bookmaker_id IS NOT NULL AND line IS NOT NULL) "
            "AS canonical_bookmaker_fixture_lines "
            "FROM policy_fixtures pf "
            "JOIN fixture_meta fm USING (fixture_id)",
            (POLICY_VERSION,) * 5,
        )
        coverage = _one(cursor)

        cursor.execute(
            "SELECT COUNT(*)::BIGINT AS evaluated_rows, "
            "COUNT(*) FILTER (WHERE edge >= 0.03)::BIGINT AS edge_ge_3pct, "
            "COUNT(*) FILTER (WHERE expected_value >= 0.03)::BIGINT AS ev_ge_3pct, "
            "COUNT(*) FILTER (WHERE edge >= 0.03 AND expected_value >= 0.03)::BIGINT "
            "AS both_ge_threshold, "
            "MIN(edge) AS edge_min, "
            "percentile_cont(0.05) WITHIN GROUP (ORDER BY edge) AS edge_p05, "
            "percentile_cont(0.50) WITHIN GROUP (ORDER BY edge) AS edge_median, "
            "AVG(edge) AS edge_mean, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY edge) AS edge_p95, "
            "MAX(edge) AS edge_max, "
            "MIN(expected_value) AS ev_min, "
            "percentile_cont(0.05) WITHIN GROUP (ORDER BY expected_value) AS ev_p05, "
            "percentile_cont(0.50) WITHIN GROUP (ORDER BY expected_value) AS ev_median, "
            "AVG(expected_value) AS ev_mean, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY expected_value) AS ev_p95, "
            "MAX(expected_value) AS ev_max "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s AND model_probability IS NOT NULL",
            (POLICY_VERSION,),
        )
        value_summary = _one(cursor)

        cursor.execute(
            "SELECT selection, COUNT(*)::BIGINT AS row_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s AND model_probability IS NOT NULL "
            "GROUP BY selection ORDER BY selection",
            (POLICY_VERSION,),
        )
        value_by_selection = _rows(cursor)

        cursor.execute(
            "SELECT line, selection, COUNT(*)::BIGINT AS row_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count, "
            "COUNT(*) FILTER (WHERE decision = 'PICK' "
            " AND reason = 'VALUE_THRESHOLD_PASSED')::BIGINT AS pick_count, "
            "COUNT(*) FILTER (WHERE decision = 'PICK' "
            " AND reason = 'VALUE_THRESHOLD_PASSED')::NUMERIC "
            "/ NULLIF(COUNT(*), 0) AS pick_rate, "
            "MIN(model_probability) AS model_p_min, "
            "percentile_cont(0.05) WITHIN GROUP (ORDER BY model_probability) AS model_p_p05, "
            "percentile_cont(0.50) WITHIN GROUP (ORDER BY model_probability) AS model_p_median, "
            "AVG(model_probability) AS model_p_mean, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY model_probability) AS model_p_p95, "
            "MAX(model_probability) AS model_p_max, "
            "MIN(edge) AS edge_min, "
            "percentile_cont(0.05) WITHIN GROUP (ORDER BY edge) AS edge_p05, "
            "percentile_cont(0.50) WITHIN GROUP (ORDER BY edge) AS edge_median, "
            "AVG(edge) AS edge_mean, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY edge) AS edge_p95, "
            "MAX(edge) AS edge_max, "
            "MIN(expected_value) AS ev_min, "
            "percentile_cont(0.05) WITHIN GROUP (ORDER BY expected_value) AS ev_p05, "
            "percentile_cont(0.50) WITHIN GROUP (ORDER BY expected_value) AS ev_median, "
            "AVG(expected_value) AS ev_mean, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY expected_value) AS ev_p95, "
            "MAX(expected_value) AS ev_max "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s AND line IS NOT NULL AND model_probability IS NOT NULL "
            "GROUP BY line, selection ORDER BY line, selection LIMIT 80",
            (POLICY_VERSION,),
        )
        value_by_line_and_selection = _rows(cursor)

        cursor.execute(
            "SELECT bookmaker_name, selection, COUNT(*)::BIGINT AS row_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count, "
            "COUNT(*) FILTER (WHERE decision = 'PICK' "
            " AND reason = 'VALUE_THRESHOLD_PASSED')::BIGINT AS pick_count, "
            "COUNT(*) FILTER (WHERE decision = 'PICK' "
            " AND reason = 'VALUE_THRESHOLD_PASSED')::NUMERIC "
            "/ NULLIF(COUNT(*), 0) AS pick_rate, "
            "AVG(model_probability) AS mean_model_probability, "
            "AVG(edge) AS mean_edge, AVG(expected_value) AS mean_ev "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s AND bookmaker_name IS NOT NULL "
            "AND model_probability IS NOT NULL "
            "GROUP BY bookmaker_name, selection "
            "ORDER BY bookmaker_name, selection",
            (POLICY_VERSION,),
        )
        value_by_bookmaker_and_selection = _rows(cursor)

        cursor.execute(
            "SELECT COUNT(*)::BIGINT AS decision_rows, "
            "COUNT(*) FILTER (WHERE d.model_version IS NULL)::BIGINT AS decisions_null_model_version, "
            "COUNT(DISTINCT d.model_version) FILTER (WHERE d.model_version IS NOT NULL)::BIGINT "
            "AS distinct_decision_model_versions, "
            "COUNT(*) FILTER (WHERE d.model_version IS NOT NULL AND m.model_version IS NULL)::BIGINT "
            "AS decision_model_version_not_in_artifacts "
            "FROM quantlab_context_market_decisions d "
            "LEFT JOIN quantlab_corner_model_versions m ON m.model_version = d.model_version "
            "WHERE d.policy_version = %s",
            (POLICY_VERSION,),
        )
        model_refs = _one(cursor)

        cursor.execute(
            "SELECT model_version, COUNT(*)::BIGINT AS row_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s AND model_version IS NOT NULL "
            "GROUP BY model_version ORDER BY row_count DESC, model_version LIMIT 20",
            (POLICY_VERSION,),
        )
        decisions_by_model = _rows(cursor)

        cursor.execute(
            "WITH active_model AS ("
            " SELECT model_version FROM quantlab_corner_model_versions "
            " ORDER BY trained_at DESC, model_version DESC LIMIT 1"
            "), active_picks AS ("
            " SELECT d.* FROM quantlab_context_market_decisions d "
            " JOIN active_model m ON m.model_version = d.model_version "
            " WHERE d.policy_version = %s AND d.decision = 'PICK' "
            " AND d.reason = 'VALUE_THRESHOLD_PASSED'"
            ") "
            "SELECT COUNT(*)::BIGINT AS row_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count, "
            "COUNT(DISTINCT (fixture_id, line))::BIGINT AS fixture_line_count, "
            "MIN(model_version) AS model_version "
            "FROM active_picks",
            (POLICY_VERSION,),
        )
        active_pick_summary = _one(cursor)

        cursor.execute(
            "WITH active_model AS ("
            " SELECT model_version FROM quantlab_corner_model_versions "
            " ORDER BY trained_at DESC, model_version DESC LIMIT 1"
            "), active_picks AS ("
            " SELECT d.* FROM quantlab_context_market_decisions d "
            " JOIN active_model m ON m.model_version = d.model_version "
            " WHERE d.policy_version = %s AND d.decision = 'PICK' "
            " AND d.reason = 'VALUE_THRESHOLD_PASSED'"
            ") "
            "SELECT d.fixture_id, "
            "COALESCE(q.home_team, p.home_team) AS home_team, "
            "COALESCE(q.away_team, p.away_team) AS away_team, "
            "COALESCE(q.competition_name, p.competition_name) AS competition_name, "
            "COALESCE(q.country, p.country) AS country, "
            "COALESCE(q.kickoff_at, p.kickoff_at) AS kickoff_at, "
            "COUNT(*)::BIGINT AS pick_rows, "
            "COUNT(DISTINCT d.line)::BIGINT AS distinct_lines "
            "FROM active_picks d "
            "LEFT JOIN LATERAL ("
            " SELECT home_team, away_team, competition_name, country, kickoff_at "
            " FROM quantlab_fixture_observations o WHERE o.fixture_id = d.fixture_id "
            " ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
            ") q ON TRUE "
            "LEFT JOIN LATERAL ("
            " SELECT home_team, away_team, competition_name, country, kickoff_at "
            " FROM fixture_observations o WHERE o.fixture_id = d.fixture_id "
            " ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
            ") p ON TRUE "
            "GROUP BY d.fixture_id, q.home_team, p.home_team, q.away_team, p.away_team, "
            "q.competition_name, p.competition_name, q.country, p.country, "
            "q.kickoff_at, p.kickoff_at "
            "ORDER BY kickoff_at, d.fixture_id",
            (POLICY_VERSION,),
        )
        active_pick_by_fixture = _rows(cursor)

        cursor.execute(
            "WITH active_model AS ("
            " SELECT model_version FROM quantlab_corner_model_versions "
            " ORDER BY trained_at DESC, model_version DESC LIMIT 1"
            "), active_picks AS ("
            " SELECT d.* FROM quantlab_context_market_decisions d "
            " JOIN active_model m ON m.model_version = d.model_version "
            " WHERE d.policy_version = %s AND d.decision = 'PICK' "
            " AND d.reason = 'VALUE_THRESHOLD_PASSED'"
            ") "
            "SELECT d.decision_at, d.fixture_id, "
            "COALESCE(q.home_team, p.home_team) AS home_team, "
            "COALESCE(q.away_team, p.away_team) AS away_team, "
            "COALESCE(q.competition_name, p.competition_name) AS competition_name, "
            "COALESCE(q.country, p.country) AS country, "
            "COALESCE(q.kickoff_at, p.kickoff_at) AS kickoff_at, "
            "d.bookmaker_id, d.bookmaker_name, d.provider_bet_name, d.line, d.selection, "
            "d.model_probability, d.market_probability, d.edge, d.expected_value, "
            "d.odds, d.companion_odds, "
            "(d.details->>'expected_total_corners')::NUMERIC AS expected_total_corners, "
            "(d.details->>'home_history_size')::BIGINT AS home_history_size, "
            "(d.details->>'away_history_size')::BIGINT AS away_history_size, "
            "d.model_version "
            "FROM active_picks d "
            "LEFT JOIN LATERAL ("
            " SELECT home_team, away_team, competition_name, country, kickoff_at "
            " FROM quantlab_fixture_observations o WHERE o.fixture_id = d.fixture_id "
            " ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
            ") q ON TRUE "
            "LEFT JOIN LATERAL ("
            " SELECT home_team, away_team, competition_name, country, kickoff_at "
            " FROM fixture_observations o WHERE o.fixture_id = d.fixture_id "
            " ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
            ") p ON TRUE "
            "ORDER BY kickoff_at, d.fixture_id, d.line, d.selection, "
            "d.bookmaker_id, d.decision_at LIMIT 500",
            (POLICY_VERSION,),
        )
        active_pick_rows = _rows(cursor)
        active_pick_summary = {
            **active_pick_summary,
            "returned_rows": len(active_pick_rows),
            "truncated": int(active_pick_summary.get("row_count") or 0) > len(active_pick_rows),
        }

        fixture_meta_cte = (
            "WITH fixture_meta AS ("
            " SELECT f.fixture_id, "
            " COALESCE(q.kickoff_at, p.kickoff_at) AS kickoff_at, "
            " COALESCE(q.competition_name, p.competition_name) AS competition_name "
            " FROM quantlab_fixtures f "
            " LEFT JOIN LATERAL ("
            "  SELECT kickoff_at, competition_name FROM quantlab_fixture_observations o "
            "  WHERE o.fixture_id = f.fixture_id "
            "  ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
            " ) q ON TRUE "
            " LEFT JOIN LATERAL ("
            "  SELECT kickoff_at, competition_name FROM fixture_observations o "
            "  WHERE o.fixture_id = f.fixture_id "
            "  ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
            " ) p ON TRUE"
            "), actual AS ("
            " SELECT DISTINCT ON (fixture_id) fixture_id, "
            " home_corner_kicks + away_corner_kicks AS actual_total_corners, available_at "
            " FROM quantlab_match_statistics_observations "
            " WHERE home_corner_kicks IS NOT NULL AND away_corner_kicks IS NOT NULL "
            " ORDER BY fixture_id, available_at DESC, statistics_observation_id DESC"
            ") "
        )

        cursor.execute(
            fixture_meta_cte
            + ", chosen AS ("
            " SELECT DISTINCT ON (s.fixture_id) s.fixture_id, s.decision_at, "
            " s.expected_total_corners, fm.kickoff_at, fm.competition_name "
            " FROM quantlab_corner_feature_snapshots s "
            " JOIN fixture_meta fm USING (fixture_id) "
            " WHERE fm.kickoff_at IS NOT NULL AND s.decision_at < fm.kickoff_at "
            " ORDER BY s.fixture_id, s.decision_at DESC, s.feature_snapshot_id DESC"
            ") "
            "SELECT c.fixture_id, c.competition_name, c.kickoff_at, c.decision_at, "
            "c.expected_total_corners, a.actual_total_corners "
            "FROM chosen c JOIN actual a USING (fixture_id) "
            "WHERE a.available_at > c.kickoff_at "
            "ORDER BY c.kickoff_at, c.fixture_id"
        )
        quality_rows = _rows(cursor)

        cursor.execute(
            fixture_meta_cte
            + ", chosen_decisions AS ("
            " SELECT DISTINCT ON (d.fixture_id, d.line, d.bookmaker_id) "
            " d.fixture_id, d.line, d.bookmaker_id, d.bookmaker_name, "
            " d.model_probability, d.decision_at, fm.kickoff_at, fm.competition_name "
            " FROM quantlab_context_market_decisions d "
            " JOIN fixture_meta fm USING (fixture_id) "
            " WHERE d.policy_version = %s AND d.selection = 'OVER' "
            " AND d.model_probability IS NOT NULL AND d.line IS NOT NULL "
            " AND fm.kickoff_at IS NOT NULL AND d.decision_at < fm.kickoff_at "
            " ORDER BY d.fixture_id, d.line, d.bookmaker_id, "
            " d.decision_at DESC, d.decision_id DESC"
            ") "
            "SELECT d.fixture_id, d.line, d.bookmaker_id, d.bookmaker_name, "
            "d.model_probability, d.decision_at, d.kickoff_at, d.competition_name, "
            "a.actual_total_corners "
            "FROM chosen_decisions d JOIN actual a USING (fixture_id) "
            "WHERE a.available_at > d.kickoff_at "
            "ORDER BY d.kickoff_at, d.fixture_id, d.line, d.bookmaker_id",
            (POLICY_VERSION,),
        )
        calibration_rows = _rows(cursor)

    return {
        "policy_version": POLICY_VERSION,
        "reason_distribution": reasons,
        "models": {
            "summary": model_summary,
            "latest": latest_models,
            "references": model_refs,
            "decisions_by_model_top20": decisions_by_model,
        },
        "snapshots": snapshots,
        "market_coverage": coverage,
        "value_filter": {
            "summary": value_summary,
            "by_selection": value_by_selection,
            "by_line_and_selection": value_by_line_and_selection,
            "by_bookmaker_and_selection": value_by_bookmaker_and_selection,
        },
        "active_model_picks": {
            "summary": active_pick_summary,
            "by_fixture": active_pick_by_fixture,
            "rows": active_pick_rows,
        },
        "quality": _quality(quality_rows),
        "calibration": _calibration(calibration_rows),
    }


def log_cornerlab_v2_audit(repository: Any, logger: logging.Logger) -> None:
    """Emit bounded structured audit sections to Railway logs."""
    report = collect_cornerlab_v2_audit(repository)
    for key in (
        "reason_distribution",
        "models",
        "snapshots",
        "market_coverage",
        "value_filter",
        "quality",
        "calibration",
    ):
        logger.info(
            "QuantLab CornerLab V2 audit section=%s payload=%s",
            key,
            json.dumps(report[key], sort_keys=True, default=str, separators=(",", ":")),
        )

    active_picks = report["active_model_picks"]
    logger.info(
        "QuantLab CornerLab V2 audit section=active_model_pick_summary payload=%s",
        json.dumps(
            {
                "summary": active_picks["summary"],
                "by_fixture": active_picks["by_fixture"],
            },
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ),
    )
    rows = active_picks["rows"]
    for start in range(0, len(rows), 25):
        logger.info(
            "QuantLab CornerLab V2 audit section=active_model_pick_rows batch=%s payload=%s",
            start // 25 + 1,
            json.dumps(
                rows[start : start + 25],
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ),
        )
