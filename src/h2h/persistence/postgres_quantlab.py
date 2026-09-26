"""Read model for QuantLab shadow bets."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


class PostgreSQLQuantLabRepository:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        connect: Callable[[], Any] | None = None,
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect

    def connect(self) -> Any:
        if self._connect_factory is not None:
            return self._connect_factory()
        import psycopg

        return psycopg.connect(self._database_url)

    def check_database(self) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.quantlab_shadow_bets')")
            return cursor.fetchone()[0] == "quantlab_shadow_bets"

    def list_bets(self, lab: str, *, limit: int = 5000) -> tuple[dict[str, Any], ...]:
        if lab not in {"GOAL", "CORNER", "CARD"}:
            raise ValueError("unsupported QuantLab lab")
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT q.shadow_bet_id, q.fixture_id, q.lab, q.bookmaker_id, "
                "q.bookmaker_name, q.provider_bet_id, q.provider_bet_name, "
                "q.market_key, q.selection, q.line, q.model_name, q.model_version, "
                "q.model_probability, q.market_probability, q.edge, q.expected_value, "
                "q.odds, q.quote_observed_at, q.decision_at, q.closing_odds, "
                "q.closing_observed_at, q.stake_minor, q.outcome, q.pnl_minor, "
                "q.settled_at, latest.home_team, latest.away_team, "
                "latest.competition_name, latest.country, latest.kickoff_at "
                "FROM quantlab_shadow_bets q "
                "JOIN LATERAL (SELECT home_team, away_team, competition_name, country, kickoff_at "
                "FROM fixture_observations o WHERE o.fixture_id = q.fixture_id "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "WHERE q.lab = %s ORDER BY q.decision_at DESC, q.shadow_bet_id DESC LIMIT %s",
                (lab, limit),
            )
            columns = tuple(item.name for item in cursor.description)
            return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())

    def api_usage_today(self) -> int:
        today = datetime.now(UTC).date()
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(request_count, 0) FROM provider_request_usage "
                "WHERE request_day = %s AND category = 'quantlab_context'",
                (today,),
            )
            row = cursor.fetchone()
            return 0 if row is None else int(row[0])
