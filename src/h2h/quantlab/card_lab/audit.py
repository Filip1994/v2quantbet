"""Read-only CardLab V4 funnel audit.

Summarizes the append-only V4 decision ledger, 1xBet Total Cards coverage,
CardLab feature coverage and value thresholds. No writes are performed.
"""

from __future__ import annotations

import json
import logging
from typing import Any


POLICY_VERSION = "CARDLAB_1XBET_POISSON_POLICY_V4"
MODEL_VERSION = "CARDLAB_REFEREE_POISSON_V1"
BOOKMAKER_ID = 11
PROVIDER_BET_ID = 119


def _rows(cursor: Any) -> tuple[dict[str, Any], ...]:
    columns = tuple(item.name for item in cursor.description)
    return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


def _one(cursor: Any) -> dict[str, Any]:
    rows = _rows(cursor)
    return {} if not rows else rows[0]


def collect_cardlab_v4_audit(repository: Any) -> dict[str, Any]:
    """Collect exact read-only CardLab V4 diagnostics from PostgreSQL."""
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
            "SELECT COUNT(*)::BIGINT AS decision_rows, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS decision_fixtures, "
            "COUNT(*) FILTER (WHERE decision = 'PICK')::BIGINT AS pick_rows, "
            "COUNT(DISTINCT fixture_id) FILTER (WHERE decision = 'PICK')::BIGINT "
            "AS pick_fixtures, "
            "COUNT(*) FILTER (WHERE model_version = %s)::BIGINT AS model_rows, "
            "MAX(decision_at) AS latest_decision_at "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s",
            (MODEL_VERSION, POLICY_VERSION),
        )
        summary = _one(cursor)

        cursor.execute(
            "SELECT selection, COUNT(*)::BIGINT AS row_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count, "
            "AVG(model_probability) AS mean_model_probability, "
            "AVG(market_probability) AS mean_market_probability, "
            "AVG(edge) AS mean_edge, AVG(expected_value) AS mean_ev, "
            "MIN(edge) AS min_edge, MAX(edge) AS max_edge, "
            "MIN(expected_value) AS min_ev, MAX(expected_value) AS max_ev, "
            "COUNT(*) FILTER (WHERE edge >= 0.03)::BIGINT AS edge_ge_3pct, "
            "COUNT(*) FILTER (WHERE expected_value >= 0.03)::BIGINT AS ev_ge_3pct, "
            "COUNT(*) FILTER (WHERE edge >= 0.03 AND expected_value >= 0.03)::BIGINT "
            "AS both_ge_3pct "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s AND provider_bet_id IS NOT NULL "
            "GROUP BY selection ORDER BY selection",
            (POLICY_VERSION,),
        )
        value_filter = _rows(cursor)

        cursor.execute(
            "WITH quote_sides AS ("
            " SELECT fixture_id, parsed_line, captured_at, "
            " BOOL_OR(LOWER(raw_selection) LIKE 'over %%') AS has_over, "
            " BOOL_OR(LOWER(raw_selection) LIKE 'under %%') AS has_under "
            " FROM quantlab_market_observations "
            " WHERE lab_owner = 'CARD' AND bookmaker_id = %s "
            " AND provider_bet_id = %s AND parsed_line IS NOT NULL "
            " GROUP BY fixture_id, parsed_line, captured_at"
            ") "
            "SELECT COUNT(*)::BIGINT AS observed_quote_snapshots, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS observed_fixtures, "
            "COUNT(*) FILTER (WHERE has_over AND has_under)::BIGINT AS complete_pairs, "
            "COUNT(DISTINCT fixture_id) FILTER (WHERE has_over AND has_under)::BIGINT "
            "AS fixtures_with_complete_pair, "
            "MAX(captured_at) AS latest_market_capture "
            "FROM quote_sides",
            (BOOKMAKER_ID, PROVIDER_BET_ID),
        )
        market_coverage = _one(cursor)

        cursor.execute(
            "SELECT bookmaker_id, bookmaker_name, provider_bet_id, provider_bet_name, "
            "COUNT(*)::BIGINT AS observation_rows, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count, "
            "MAX(captured_at) AS latest_capture "
            "FROM quantlab_market_observations "
            "WHERE lab_owner = 'CARD' "
            "GROUP BY bookmaker_id, bookmaker_name, provider_bet_id, provider_bet_name "
            "ORDER BY fixture_count DESC, observation_rows DESC, bookmaker_id, provider_bet_id "
            "LIMIT 50"
        )
        market_inventory = _rows(cursor)

        cursor.execute(
            "SELECT COUNT(*)::BIGINT AS snapshot_rows, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS snapshot_fixtures, "
            "COUNT(*) FILTER (WHERE referee_card_rate IS NOT NULL "
            "AND referee_sample_size >= 5)::BIGINT AS rows_referee_ready, "
            "COUNT(DISTINCT fixture_id) FILTER (WHERE referee_card_rate IS NOT NULL "
            "AND referee_sample_size >= 5)::BIGINT AS fixtures_referee_ready, "
            "MIN(referee_sample_size)::BIGINT AS referee_sample_min, "
            "MAX(referee_sample_size)::BIGINT AS referee_sample_max, "
            "AVG(referee_sample_size) AS referee_sample_mean, "
            "MIN(referee_card_rate) AS referee_rate_min, "
            "AVG(referee_card_rate) AS referee_rate_mean, "
            "MAX(referee_card_rate) AS referee_rate_max, "
            "MAX(decision_at) AS latest_feature_snapshot "
            "FROM quantlab_card_feature_snapshots"
        )
        feature_coverage = _one(cursor)

        cursor.execute(
            "SELECT reason, COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s AND decision = 'PASS' "
            "GROUP BY reason ORDER BY fixture_count DESC, reason",
            (POLICY_VERSION,),
        )
        pass_funnel = _rows(cursor)

    return {
        "policy_version": POLICY_VERSION,
        "model_version": MODEL_VERSION,
        "summary": summary,
        "reason_distribution": reasons,
        "pass_funnel": pass_funnel,
        "market_coverage": market_coverage,
        "market_inventory": market_inventory,
        "feature_coverage": feature_coverage,
        "value_filter": value_filter,
    }


def log_cardlab_v4_audit(repository: Any, logger: logging.Logger) -> None:
    """Emit bounded structured CardLab V4 audit sections to Railway logs."""
    report = collect_cardlab_v4_audit(repository)
    for key in (
        "summary",
        "reason_distribution",
        "pass_funnel",
        "market_coverage",
        "market_inventory",
        "feature_coverage",
        "value_filter",
    ):
        logger.info(
            "QuantLab CardLab V4 audit section=%s payload=%s",
            key,
            json.dumps(report[key], sort_keys=True, default=str, separators=(",", ":")),
        )
