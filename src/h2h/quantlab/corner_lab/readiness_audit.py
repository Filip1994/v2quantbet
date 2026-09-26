"""Read-only CornerLab V2 readiness and raw-market coverage audit."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from statistics import fmean
from typing import Any

from h2h.quantlab.corner_lab.model import (
    HISTORY_LIMIT,
    MIN_TEAM_HISTORY,
    MIN_TRAINING_EXAMPLES,
    _build_training,
)
from h2h.quantlab.corner_lab.shadow_engine import _is_half_line, _market_name_supported


POLICY_VERSION = "CORNERLAB_PRESSURE_POISSON_POLICY_V2"


def _rows(cursor: Any) -> tuple[dict[str, Any], ...]:
    columns = tuple(item.name for item in cursor.description)
    return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


def _distribution(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def quantile(p: float) -> float:
        if len(ordered) == 1:
            return float(ordered[0])
        position = (len(ordered) - 1) * p
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        weight = position - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight

    return {
        "n": len(ordered),
        "min": ordered[0],
        "p25": round(quantile(0.25), 3),
        "median": round(quantile(0.50), 3),
        "mean": round(fmean(ordered), 3),
        "p75": round(quantile(0.75), 3),
        "max": ordered[-1],
    }


def _team_id(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _market_summary(
    rows: tuple[dict[str, Any], ...],
    *,
    now: datetime,
) -> tuple[dict[str, Any], set[str]]:
    supported: list[dict[str, Any]] = []
    for row in rows:
        line = float(row["parsed_line"])
        if not _is_half_line(line):
            continue
        if not _market_name_supported(str(row["provider_bet_name"])):
            continue
        supported.append(row)

    upcoming = [
        row
        for row in supported
        if isinstance(row.get("kickoff_at"), datetime) and row["kickoff_at"] > now
    ]
    upcoming_fixture_ids = {str(row["fixture_id"]) for row in upcoming}

    bookmaker_counts: Counter[str] = Counter()
    bookmaker_fixtures: dict[str, set[str]] = {}
    line_counts: Counter[str] = Counter()
    market_name_counts: Counter[str] = Counter()
    for row in upcoming:
        bookmaker = str(row.get("bookmaker_name") or row.get("bookmaker_id") or "UNKNOWN")
        bookmaker_counts[bookmaker] += 1
        bookmaker_fixtures.setdefault(bookmaker, set()).add(str(row["fixture_id"]))
        line_counts[str(float(row["parsed_line"]))] += 1
        market_name_counts[str(row["provider_bet_name"])] += 1

    return (
        {
            "complete_two_sided_logical_pairs_before_semantic_filter": len(rows),
            "supported_full_match_half_line_pairs_all": len(supported),
            "supported_full_match_half_line_fixtures_all": len(
                {str(row["fixture_id"]) for row in supported}
            ),
            "supported_upcoming_pairs": len(upcoming),
            "supported_upcoming_fixtures": len(upcoming_fixture_ids),
            "upcoming_pairs_by_bookmaker": [
                {
                    "bookmaker": bookmaker,
                    "pair_count": count,
                    "fixture_count": len(bookmaker_fixtures[bookmaker]),
                }
                for bookmaker, count in bookmaker_counts.most_common()
            ],
            "upcoming_lines_top20": [
                {"line": line, "pair_count": count}
                for line, count in line_counts.most_common(20)
            ],
            "upcoming_provider_market_names_top20": [
                {"provider_bet_name": name, "pair_count": count}
                for name, count in market_name_counts.most_common(20)
            ],
        },
        upcoming_fixture_ids,
    )


def collect_cornerlab_v2_readiness(repository: Any) -> dict[str, Any]:
    """Use the exact CornerLab training builder plus raw persisted odds for readiness."""
    now = datetime.now(UTC)
    history_rows = repository.corner_model_history(before=now, limit=HISTORY_LIMIT)
    _x, y, histories, history_match_count = _build_training(history_rows)

    with repository.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT decision_at, details "
            "FROM quantlab_context_market_decisions "
            "WHERE policy_version = %s AND reason = 'INSUFFICIENT_CORNER_MODEL_HISTORY' "
            "ORDER BY decision_at DESC, decision_id DESC LIMIT 1",
            (POLICY_VERSION,),
        )
        latest_pass_row = cursor.fetchone()
        latest_pass = None
        if latest_pass_row is not None:
            details = latest_pass_row[1]
            if isinstance(details, str):
                details = json.loads(details)
            latest_pass = {
                "decision_at": latest_pass_row[0],
                "details": details,
            }

        cursor.execute(
            "WITH policy_fixtures AS ("
            " SELECT DISTINCT fixture_id FROM quantlab_context_market_decisions "
            " WHERE policy_version = %s"
            ") "
            "SELECT pf.fixture_id, "
            "COALESCE(q.kickoff_at, p.kickoff_at) AS kickoff_at, "
            "COALESCE(q.home_team_id, f.provider_home_team_id::BIGINT) AS home_team_id, "
            "COALESCE(q.away_team_id, f.provider_away_team_id::BIGINT) AS away_team_id "
            "FROM policy_fixtures pf "
            "JOIN quantlab_fixtures f USING (fixture_id) "
            "LEFT JOIN LATERAL ("
            " SELECT kickoff_at, home_team_id, away_team_id "
            " FROM quantlab_fixture_observations o "
            " WHERE o.fixture_id = pf.fixture_id "
            " ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
            ") q ON TRUE "
            "LEFT JOIN LATERAL ("
            " SELECT kickoff_at FROM fixture_observations o "
            " WHERE o.fixture_id = pf.fixture_id "
            " ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
            ") p ON TRUE "
            "WHERE COALESCE(q.kickoff_at, p.kickoff_at) > %s "
            "ORDER BY COALESCE(q.kickoff_at, p.kickoff_at), pf.fixture_id",
            (POLICY_VERSION, now),
        )
        upcoming_targets = _rows(cursor)

        cursor.execute(
            "WITH policy_fixtures AS ("
            " SELECT DISTINCT fixture_id FROM quantlab_context_market_decisions "
            " WHERE policy_version = %s"
            "), fixture_meta AS ("
            " SELECT pf.fixture_id, COALESCE(q.kickoff_at, p.kickoff_at) AS kickoff_at "
            " FROM policy_fixtures pf "
            " LEFT JOIN LATERAL ("
            "  SELECT kickoff_at FROM quantlab_fixture_observations o "
            "  WHERE o.fixture_id = pf.fixture_id "
            "  ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
            " ) q ON TRUE "
            " LEFT JOIN LATERAL ("
            "  SELECT kickoff_at FROM fixture_observations o "
            "  WHERE o.fixture_id = pf.fixture_id "
            "  ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
            " ) p ON TRUE"
            "), complete AS ("
            " SELECT o.fixture_id, o.bookmaker_id, o.bookmaker_name, "
            " o.provider_bet_id, o.provider_bet_name, o.parsed_line, o.captured_at "
            " FROM quantlab_market_observations o "
            " JOIN policy_fixtures pf USING (fixture_id) "
            " WHERE o.lab_owner = 'CORNER' AND o.parsed_line IS NOT NULL "
            " GROUP BY o.fixture_id, o.bookmaker_id, o.bookmaker_name, "
            " o.provider_bet_id, o.provider_bet_name, o.parsed_line, o.captured_at "
            " HAVING bool_or(lower(trim(o.raw_selection)) LIKE 'over %%') "
            " AND bool_or(lower(trim(o.raw_selection)) LIKE 'under %%')"
            "), latest AS ("
            " SELECT DISTINCT ON (fixture_id, bookmaker_id, provider_bet_id, "
            " lower(provider_bet_name), parsed_line) "
            " fixture_id, bookmaker_id, bookmaker_name, provider_bet_id, "
            " provider_bet_name, parsed_line, captured_at "
            " FROM complete "
            " ORDER BY fixture_id, bookmaker_id, provider_bet_id, "
            " lower(provider_bet_name), parsed_line, captured_at DESC"
            ") "
            "SELECT l.*, fm.kickoff_at "
            "FROM latest l LEFT JOIN fixture_meta fm USING (fixture_id) "
            "ORDER BY l.fixture_id, l.bookmaker_id, l.provider_bet_id, l.parsed_line",
            (POLICY_VERSION,),
        )
        raw_market_pairs = _rows(cursor)

        cursor.execute(
            "SELECT status, COUNT(*)::BIGINT AS capture_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count "
            "FROM quantlab_statistics_captures "
            "GROUP BY status ORDER BY status"
        )
        statistics_capture_status = _rows(cursor)

        cursor.execute(
            "SELECT COUNT(*)::BIGINT AS observation_count, "
            "COUNT(DISTINCT fixture_id)::BIGINT AS fixture_count, "
            "COUNT(*) FILTER (WHERE home_corner_kicks IS NOT NULL "
            "AND away_corner_kicks IS NOT NULL)::BIGINT AS rows_with_corner_totals, "
            "COUNT(DISTINCT fixture_id) FILTER (WHERE home_corner_kicks IS NOT NULL "
            "AND away_corner_kicks IS NOT NULL)::BIGINT AS fixtures_with_corner_totals "
            "FROM quantlab_match_statistics_observations"
        )
        columns = tuple(item.name for item in cursor.description)
        statistics_observations = dict(zip(columns, cursor.fetchone(), strict=True))

    home_sizes: list[int] = []
    away_sizes: list[int] = []
    sufficient_fixture_ids: set[str] = set()
    missing_team_identities = 0
    for row in upcoming_targets:
        home_id = _team_id(row.get("home_team_id"))
        away_id = _team_id(row.get("away_team_id"))
        if home_id is None or away_id is None or home_id == away_id:
            missing_team_identities += 1
            continue
        home_size = len(histories.get(home_id, []))
        away_size = len(histories.get(away_id, []))
        home_sizes.append(home_size)
        away_sizes.append(away_size)
        if home_size >= MIN_TEAM_HISTORY and away_size >= MIN_TEAM_HISTORY:
            sufficient_fixture_ids.add(str(row["fixture_id"]))

    market_summary, supported_upcoming_fixture_ids = _market_summary(
        raw_market_pairs,
        now=now,
    )

    return {
        "as_of": now,
        "current_training_readiness": {
            "history_rows_loaded": len(history_rows),
            "history_match_count": history_match_count,
            "training_sample_size": len(y),
            "minimum_training_examples": MIN_TRAINING_EXAMPLES,
            "training_shortfall": max(0, MIN_TRAINING_EXAMPLES - len(y)),
            "model_fit_eligible": len(y) >= MIN_TRAINING_EXAMPLES,
            "history_limit": HISTORY_LIMIT,
            "latest_insufficient_model_pass": latest_pass,
        },
        "upcoming_team_history": {
            "upcoming_policy_fixtures": len(upcoming_targets),
            "missing_team_identities": missing_team_identities,
            "fixtures_both_team_history_ge_minimum": len(sufficient_fixture_ids),
            "minimum_team_history": MIN_TEAM_HISTORY,
            "home_history_size": _distribution(home_sizes),
            "away_history_size": _distribution(away_sizes),
        },
        "raw_canonical_corner_markets": {
            **market_summary,
            "upcoming_fixtures_with_sufficient_team_history_and_supported_market": len(
                sufficient_fixture_ids & supported_upcoming_fixture_ids
            ),
        },
        "statistics_coverage": {
            "capture_status": statistics_capture_status,
            "observations": statistics_observations,
        },
    }


def log_cornerlab_v2_readiness(repository: Any, logger: logging.Logger) -> None:
    report = collect_cornerlab_v2_readiness(repository)
    logger.info(
        "QuantLab CornerLab V2 readiness payload=%s",
        json.dumps(report, sort_keys=True, default=str, separators=(",", ":")),
    )
