"""Durable final-gate research candidates and read-only research projection."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


ConnectionFactory = Callable[[], Any]
_EVALUATION_ID = re.compile(r"^value-evaluation-v1:[0-9a-f]{64}$")


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def research_signal_id(evaluation_id: str) -> str:
    if not isinstance(evaluation_id, str) or _EVALUATION_ID.fullmatch(evaluation_id) is None:
        raise ValueError("evaluation_id must be a durable value-evaluation-v1 identifier")
    return "research-signal-v1:" + evaluation_id.split(":", 1)[1]


class PostgreSQLResearchSignalRepository:
    """Research-only storage. It never writes bankroll, pick or risk tables."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        connect: ConnectionFactory | None = None,
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect

    def connect(self) -> Any:
        if self._connect_factory is not None:
            return self._connect_factory()
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg[binary]") from exc
        return psycopg.connect(self._database_url)

    def check_database(self) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('research_signals') IS NOT NULL")
            row = cursor.fetchone()
            return bool(row and row[0])

    def record_exposure_blocked(
        self,
        evaluation_id: str,
        *,
        blocked_at: datetime,
        open_exposure_minor: int,
        exposure_cap_minor: int,
    ) -> str:
        signal_id = research_signal_id(evaluation_id)
        blocked = _utc(blocked_at, "blocked_at")
        for name, value, allow_zero in (
            ("open_exposure_minor", open_exposure_minor, True),
            ("exposure_cap_minor", exposure_cap_minor, False),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0 or (not allow_zero and value == 0):
                raise ValueError(f"{name} is out of range")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO research_signals (research_signal_id, evaluation_id, fixture_id, "
                "stage, block_reason, first_blocked_at, last_blocked_at, blocked_count, "
                "first_open_exposure_minor, last_open_exposure_minor, exposure_cap_minor, "
                "qualified_at) "
                "SELECT %s, e.evaluation_id, e.fixture_id, 'PRELIMINARY', "
                "'MAX_OPEN_EXPOSURE_EXCEEDED', %s, %s, 1, %s, %s, %s, %s "
                "FROM value_evaluations e WHERE e.evaluation_id = %s "
                "ON CONFLICT (fixture_id) DO UPDATE SET "
                "first_open_exposure_minor = CASE WHEN research_signals.first_blocked_at "
                "IS NULL OR EXCLUDED.first_blocked_at < research_signals.first_blocked_at "
                "THEN EXCLUDED.first_open_exposure_minor "
                "ELSE research_signals.first_open_exposure_minor END, "
                "last_open_exposure_minor = CASE WHEN research_signals.last_blocked_at "
                "IS NULL OR EXCLUDED.last_blocked_at >= research_signals.last_blocked_at "
                "THEN EXCLUDED.last_open_exposure_minor "
                "ELSE research_signals.last_open_exposure_minor END, "
                "first_blocked_at = LEAST(research_signals.first_blocked_at, "
                "EXCLUDED.first_blocked_at), "
                "last_blocked_at = GREATEST(research_signals.last_blocked_at, "
                "EXCLUDED.last_blocked_at), "
                "blocked_count = COALESCE(research_signals.blocked_count, 0) + 1, "
                "block_reason = 'MAX_OPEN_EXPOSURE_EXCEEDED', "
                "exposure_cap_minor = EXCLUDED.exposure_cap_minor, "
                "qualified_at = LEAST(research_signals.qualified_at, EXCLUDED.qualified_at) "
                "RETURNING research_signal_id",
                (
                    signal_id,
                    blocked,
                    blocked,
                    open_exposure_minor,
                    open_exposure_minor,
                    exposure_cap_minor,
                    blocked,
                    evaluation_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"value evaluation {evaluation_id!r} does not exist")
            return str(row[0])

    def record_production_candidate(
        self,
        evaluation_id: str,
        *,
        qualified_at: datetime,
        production_pick_id: str,
    ) -> str:
        signal_id = research_signal_id(evaluation_id)
        qualified = _utc(qualified_at, "qualified_at")
        if not isinstance(production_pick_id, str) or not production_pick_id.strip():
            raise ValueError("production_pick_id must be a non-empty string")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO research_signals (research_signal_id, evaluation_id, fixture_id, "
                "stage, block_reason, first_blocked_at, last_blocked_at, blocked_count, "
                "first_open_exposure_minor, last_open_exposure_minor, exposure_cap_minor, "
                "qualified_at, production_pick_id) "
                "SELECT %s, e.evaluation_id, e.fixture_id, 'PRELIMINARY', NULL, NULL, NULL, "
                "NULL, NULL, NULL, NULL, %s, %s FROM value_evaluations e "
                "WHERE e.evaluation_id = %s "
                "ON CONFLICT (fixture_id) DO UPDATE SET "
                "research_signal_id = EXCLUDED.research_signal_id, "
                "evaluation_id = EXCLUDED.evaluation_id, "
                "production_pick_id = EXCLUDED.production_pick_id, "
                "qualified_at = EXCLUDED.qualified_at, "
                "block_reason = NULL, first_blocked_at = NULL, last_blocked_at = NULL, "
                "blocked_count = NULL, first_open_exposure_minor = NULL, "
                "last_open_exposure_minor = NULL, exposure_cap_minor = NULL "
                "RETURNING research_signal_id",
                (signal_id, qualified, production_pick_id.strip(), evaluation_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"value evaluation {evaluation_id!r} does not exist")
            return str(row[0])

    def list_signals(self, *, limit: int = 1000) -> tuple[dict[str, Any], ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT rs.research_signal_id, rs.evaluation_id, rs.fixture_id, "
                "f.provider_fixture_id, f.league_id, f.season, rs.stage, rs.block_reason, "
                "rs.first_blocked_at, rs.last_blocked_at, rs.blocked_count, "
                "rs.first_open_exposure_minor, rs.last_open_exposure_minor, "
                "rs.exposure_cap_minor, rs.qualified_at, rs.production_pick_id, "
                "CASE WHEN rs.production_pick_id IS NULL THEN 'BLOCKED_EXPOSURE' "
                "ELSE COALESCE(operator_state.state, 'PLAYED') END, "
                "latest.home_team, latest.away_team, "
                "latest.competition_name, latest.country, latest.kickoff_at, "
                "latest.provider_status, e.market, e.selected_selection, e.bookmaker_key, "
                "e.model_probability, e.selected_devig_probability, e.selected_odd, "
                "e.edge, e.expected_value, e.quote_observed_at, e.selected_captured_at, "
                "e.source, closing.odd, closing.observed_at, closing.captured_at, "
                "state.phase, result.result_classification, result.provider_status, "
                "result.regulation_home_goals, result.regulation_away_goals "
                "FROM research_signals rs "
                "JOIN value_evaluations e ON e.evaluation_id = rs.evaluation_id "
                "JOIN fixtures f ON f.fixture_id = e.fixture_id "
                "JOIN LATERAL (SELECT fo.home_team, fo.away_team, fo.competition_name, "
                "fo.country, fo.kickoff_at, fo.provider_status "
                "FROM fixture_observations fo WHERE fo.fixture_id = e.fixture_id "
                "ORDER BY fo.observed_at DESC, fo.fixture_observation_id DESC LIMIT 1) "
                "latest ON TRUE "
                "LEFT JOIN LATERAL (SELECT q.odd, q.observed_at, q.captured_at "
                "FROM quote_snapshots q WHERE q.series_id = e.selected_series_id "
                "AND q.source = e.source AND q.observed_at < latest.kickoff_at "
                "ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC LIMIT 1) "
                "closing ON TRUE "
                "LEFT JOIN LATERAL (SELECT op.state FROM pick_operator_state_events op "
                "WHERE op.pick_id = rs.production_pick_id "
                "ORDER BY op.occurred_at DESC, op.persisted_at DESC, op.event_id DESC LIMIT 1) "
                "operator_state ON TRUE "
                "LEFT JOIN fixture_result_acquisition_states state "
                "ON state.fixture_id = e.fixture_id "
                "LEFT JOIN fixture_result_observations result "
                "ON result.result_observation_id = state.current_observation_id "
                "ORDER BY rs.qualified_at DESC, rs.evaluation_id DESC LIMIT %s",
                (limit,),
            )
            columns = (
                "research_signal_id", "evaluation_id", "fixture_id", "provider_fixture_id",
                "league_id", "season", "stage", "block_reason", "first_blocked_at",
                "last_blocked_at", "blocked_count", "first_open_exposure_minor",
                "last_open_exposure_minor", "exposure_cap_minor", "qualified_at",
                "production_pick_id", "disposition", "home_team", "away_team",
                "competition_name", "country", "kickoff_at", "fixture_status", "market",
                "selection", "bookmaker", "model_probability", "market_fair_probability",
                "odds", "edge", "expected_value", "quote_observed_at", "quote_captured_at",
                "source", "closing_odds", "closing_observed_at", "closing_captured_at",
                "result_phase", "result_classification", "result_provider_status",
                "regulation_home_goals", "regulation_away_goals",
            )
            return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())
