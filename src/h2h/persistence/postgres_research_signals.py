"""Read-only research projection for exposure-blocked QuantBet signals."""

from __future__ import annotations

import os
from collections.abc import Callable
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from h2h.domain.odds import Market, Selection
from h2h.domain.settlement import realized_clv_ppm


ConnectionFactory = Callable[[], Any]


class PostgreSQLResearchSignalRepository:
    """Project shadow signals without touching bankroll or registered-pick state."""

    def __init__(
        self, database_url: str | None = None, *, connect: ConnectionFactory | None = None
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

    def signals(
        self, *, limit: int = 2000, provider_fixture_id: str | None = None
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        fixture_filter = "" if provider_fixture_id is None else "AND f.provider_fixture_id = %s "
        params: list[object] = []
        if provider_fixture_id is not None:
            value = str(provider_fixture_id).strip()
            if not value.isdigit() or int(value) <= 0:
                raise ValueError("provider_fixture_id must be a positive integer")
            params.append(value)
        params.append(limit)
        sql = """
            WITH latest_fixture AS (
                SELECT DISTINCT ON (fo.fixture_id)
                    fo.fixture_id, fo.home_team, fo.away_team, fo.competition_name,
                    fo.country, fo.kickoff_at, fo.provider_status
                FROM fixture_observations fo
                ORDER BY fo.fixture_id, fo.observed_at DESC, fo.fixture_observation_id DESC
            )
            SELECT
                s.evaluation_id, s.blocked_at, s.open_exposure_minor,
                s.proposed_stake_minor, s.max_open_exposure_minor, s.capture_source,
                f.provider_fixture_id, f.league_id, f.season,
                lf.home_team, lf.away_team, lf.competition_name, lf.country,
                lf.kickoff_at, lf.provider_status,
                e.bookmaker_key, e.market, e.selected_selection, e.selected_odd,
                e.selected_devig_probability, e.model_probability, e.edge,
                e.expected_value, e.quote_observed_at, e.source, e.selected_series_id,
                closing.snapshot_id, closing.odd, closing.observed_at, closing.captured_at,
                ro.result_classification, ro.regulation_home_goals, ro.regulation_away_goals,
                registered.pick_id, registered.registered_at,
                registered.market, registered.selection
            FROM research_exposure_blocked_signals s
            JOIN value_evaluations e ON e.evaluation_id = s.evaluation_id
            JOIN fixtures f ON f.fixture_id = s.fixture_id
            JOIN latest_fixture lf ON lf.fixture_id = s.fixture_id
            LEFT JOIN LATERAL (
                SELECT q.snapshot_id, q.odd, q.observed_at, q.captured_at
                FROM quote_snapshots q
                WHERE q.series_id = e.selected_series_id
                  AND q.source = e.source
                  AND q.observed_at < lf.kickoff_at
                  AND q.captured_at < lf.kickoff_at
                ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC
                LIMIT 1
            ) closing ON TRUE
            LEFT JOIN fixture_result_acquisition_states ras
                ON ras.fixture_id = s.fixture_id
            LEFT JOIN fixture_result_observations ro
                ON ro.result_observation_id = ras.current_observation_id
               AND ras.phase = 'COMPLETE'
            LEFT JOIN LATERAL (
                SELECT rp.pick_id, rp.registered_at, rp.market, rp.selection
                FROM registered_picks rp
                WHERE rp.fixture_id = s.fixture_id
                ORDER BY rp.registered_at, rp.pick_id
                LIMIT 1
            ) registered ON TRUE
            WHERE 1 = 1
        """ + fixture_filter + """
            ORDER BY s.blocked_at DESC, s.evaluation_id
            LIMIT %s
        """
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _outcome(
        market: str,
        selection: str,
        classification: str | None,
        home_goals: int | None,
        away_goals: int | None,
    ) -> str | None:
        if classification == "NON_PLAYED_VOIDABLE":
            return "VOID"
        if classification != "PLAYED_SETTLEABLE":
            return None
        if home_goals is None or away_goals is None:
            return None
        total = int(home_goals) + int(away_goals)
        if market == Market.OU_25.value:
            won = total >= 3 if selection == Selection.OVER.value else total <= 2
        elif market == Market.BTTS.value:
            won = (
                home_goals >= 1 and away_goals >= 1
                if selection == Selection.YES.value
                else home_goals == 0 or away_goals == 0
            )
        else:
            return None
        return "WIN" if won else "LOSS"

    @staticmethod
    def _pnl(stake_minor: int, odd: float, outcome: str | None) -> int | None:
        if outcome is None:
            return None
        if outcome == "VOID":
            return 0
        if outcome == "LOSS":
            return -int(stake_minor)
        gross = (Decimal(stake_minor) * Decimal(str(odd))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return int(gross) - int(stake_minor)

    @classmethod
    def _row(cls, row: tuple[Any, ...]) -> dict[str, Any]:
        closing_odd = None if row[27] is None else float(row[27])
        entry_odd = float(row[18])
        outcome = cls._outcome(row[16], row[17], row[30], row[31], row[32])
        clv_ppm = (
            None
            if closing_odd is None
            else realized_clv_ppm(Decimal(str(entry_odd)), Decimal(str(closing_odd)))
        )
        return {
            "evaluation_id": row[0],
            "blocked_at": row[1],
            "open_exposure_minor": int(row[2]),
            "proposed_stake_minor": int(row[3]),
            "max_open_exposure_minor": int(row[4]),
            "capture_source": row[5],
            "provider_fixture_id": str(row[6]),
            "league_id": int(row[7]),
            "season": int(row[8]),
            "home_team": row[9],
            "away_team": row[10],
            "competition_name": row[11],
            "country": row[12],
            "kickoff_at": row[13],
            "provider_status": row[14],
            "bookmaker_key": row[15],
            "market": row[16],
            "selection": row[17],
            "entry_odd": entry_odd,
            "market_fair_probability": float(row[19]),
            "model_probability": float(row[20]),
            "edge": float(row[21]),
            "expected_value": float(row[22]),
            "quote_observed_at": row[23],
            "source": row[24],
            "selected_series_id": row[25],
            "shadow_closing_snapshot_id": row[26],
            "shadow_closing_odd": closing_odd,
            "shadow_closing_observed_at": row[28],
            "shadow_closing_captured_at": row[29],
            "shadow_clv_ppm": clv_ppm,
            "result_classification": row[30],
            "regulation_home_goals": row[31],
            "regulation_away_goals": row[32],
            "counterfactual_outcome": outcome,
            "counterfactual_pnl_minor": cls._pnl(int(row[3]), entry_odd, outcome),
            "eventually_registered_pick_id": row[33],
            "eventually_registered_at": row[34],
            "eventually_registered_market": row[35],
            "eventually_registered_selection": row[36],
        }
