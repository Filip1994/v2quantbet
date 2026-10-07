"""PostgreSQL persistence and read model for KellyLab Research clones."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from h2h.domain.competition_scope import is_universe_blocked_competition
from h2h.kellylab import (
    CALIBRATION_PRIOR_N,
    KELLYLAB_CONTRACT_VERSION,
    KELLY_FRACTION,
    MAX_BET_FRACTION,
    calibration_snapshot,
    edge_bucket,
    kelly_stake_plan,
    odds_bucket,
    pnl_minor,
    probability_bucket,
    row_outcome,
)
from h2h.production_buckets import is_retired_research_segment


PORTFOLIO_ID = "KELLYLAB_RESEARCH_V1"


class PostgreSQLKellyLabRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url:
            raise ValueError("DATABASE_URL is required")

    def connect(self) -> Any:
        import psycopg

        return psycopg.connect(self._database_url)

    @staticmethod
    def _row_dicts(cursor: Any) -> tuple[dict[str, Any], ...]:
        columns = [item.name for item in cursor.description]
        return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())

    def check_database(self) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('kellylab_picks') IS NOT NULL")
            row = cursor.fetchone()
            return bool(row and row[0])

    def ensure_portfolio(
        self,
        *,
        starting_bankroll_minor: int,
        flat_stake_minor: int,
        kelly_fraction: Decimal = KELLY_FRACTION,
        max_bet_fraction: Decimal = MAX_BET_FRACTION,
        calibration_prior_n: int = CALIBRATION_PRIOR_N,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        started_at = (now or datetime.now(UTC)).astimezone(UTC)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO kellylab_portfolios (
                    portfolio_id, started_at, starting_bankroll_minor, flat_stake_minor,
                    kelly_fraction, max_bet_fraction, calibration_prior_n, currency
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'RSD')
                ON CONFLICT (portfolio_id) DO NOTHING
                """,
                (
                    PORTFOLIO_ID,
                    started_at,
                    starting_bankroll_minor,
                    flat_stake_minor,
                    kelly_fraction,
                    max_bet_fraction,
                    calibration_prior_n,
                ),
            )
            cursor.execute(
                """
                SELECT portfolio_id, started_at, starting_bankroll_minor, flat_stake_minor,
                       kelly_fraction, max_bet_fraction, calibration_prior_n, currency
                FROM kellylab_portfolios
                WHERE portfolio_id = %s
                """,
                (PORTFOLIO_ID,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("KellyLab portfolio could not be initialized")
            keys = (
                "portfolio_id",
                "started_at",
                "starting_bankroll_minor",
                "flat_stake_minor",
                "kelly_fraction",
                "max_bet_fraction",
                "calibration_prior_n",
                "currency",
            )
            portfolio = dict(zip(keys, row, strict=True))

        expected = {
            "starting_bankroll_minor": int(starting_bankroll_minor),
            "flat_stake_minor": int(flat_stake_minor),
            "kelly_fraction": Decimal(kelly_fraction),
            "max_bet_fraction": Decimal(max_bet_fraction),
            "calibration_prior_n": int(calibration_prior_n),
        }
        for key, value in expected.items():
            existing = portfolio[key]
            if isinstance(value, Decimal):
                existing = Decimal(existing)
            else:
                existing = int(existing)
            if existing != value:
                raise RuntimeError(
                    f"KellyLab portfolio contract mismatch for {key}: {existing!r} != {value!r}"
                )
        return portfolio

    @staticmethod
    def _candidate_rows(cursor: Any, *, started_at: datetime) -> tuple[dict[str, Any], ...]:
        cursor.execute(
            """
            SELECT
                rs.research_signal_id,
                rs.evaluation_id,
                rs.fixture_id,
                rs.qualified_at AS source_decision_at,
                latest.kickoff_at,
                latest.home_team,
                latest.away_team,
                latest.competition_name,
                latest.country,
                f.league_id,
                e.market,
                e.selected_selection AS selection,
                e.bookmaker_key AS bookmaker,
                e.selected_odd AS odds,
                e.model_probability,
                e.selected_devig_probability AS market_fair_probability,
                e.edge,
                e.expected_value,
                e.model_version_id,
                rs.policy_config_fingerprint
            FROM research_signals rs
            JOIN value_evaluations e ON e.evaluation_id = rs.evaluation_id
            JOIN fixtures f ON f.fixture_id = rs.fixture_id
            JOIN LATERAL (
                SELECT fo.kickoff_at, fo.home_team, fo.away_team,
                       fo.competition_name, fo.country
                FROM fixture_observations fo
                WHERE fo.fixture_id = rs.fixture_id
                ORDER BY fo.observed_at DESC, fo.fixture_observation_id DESC
                LIMIT 1
            ) latest ON TRUE
            LEFT JOIN kellylab_picks kp
                ON kp.research_signal_id = rs.research_signal_id
            WHERE rs.qualified_at IS NOT NULL
              AND rs.qualified_at >= %s
              AND kp.research_signal_id IS NULL
            ORDER BY rs.qualified_at ASC, rs.research_signal_id ASC
            """,
            (started_at,),
        )
        return PostgreSQLKellyLabRepository._row_dicts(cursor)

    @staticmethod
    def _prior_rows(cursor: Any, *, cutoff: datetime) -> tuple[dict[str, Any], ...]:
        cursor.execute(
            """
            SELECT
                rs.fixture_id,
                latest.home_team,
                latest.away_team,
                latest.competition_name,
                latest.country,
                f.league_id,
                e.market,
                e.selected_selection AS selection,
                e.selected_odd AS odds,
                e.model_probability,
                e.edge,
                result.result_classification,
                result.regulation_home_goals,
                result.regulation_away_goals,
                result.first_acquired_at
            FROM research_signals rs
            JOIN value_evaluations e ON e.evaluation_id = rs.evaluation_id
            JOIN fixtures f ON f.fixture_id = rs.fixture_id
            JOIN LATERAL (
                SELECT fo.home_team, fo.away_team, fo.competition_name, fo.country
                FROM fixture_observations fo
                WHERE fo.fixture_id = rs.fixture_id
                ORDER BY fo.observed_at DESC, fo.fixture_observation_id DESC
                LIMIT 1
            ) latest ON TRUE
            JOIN LATERAL (
                SELECT r.result_classification, r.regulation_home_goals,
                       r.regulation_away_goals, r.first_acquired_at
                FROM fixture_result_observations r
                WHERE r.fixture_id = rs.fixture_id
                  AND r.first_acquired_at < %s
                  AND r.result_classification IN (
                      'PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE'
                  )
                ORDER BY r.first_acquired_at DESC, r.result_observation_id DESC
                LIMIT 1
            ) result ON TRUE
            WHERE rs.qualified_at IS NOT NULL
              AND rs.qualified_at < %s
            """,
            (cutoff, cutoff),
        )
        rows = PostgreSQLKellyLabRepository._row_dicts(cursor)
        return tuple(
            row
            for row in rows
            if not is_universe_blocked_competition(
                country=row.get("country"),
                competition_name=row.get("competition_name"),
                league_id=row.get("league_id"),
                home_team=row.get("home_team"),
                away_team=row.get("away_team"),
            )
            and not is_retired_research_segment(row)
        )

    @staticmethod
    def _bankroll_before(
        cursor: Any,
        *,
        cutoff: datetime,
        starting_bankroll_minor: int,
    ) -> int:
        cursor.execute(
            """
            SELECT
                kp.stake_minor,
                kp.odds,
                result.result_classification,
                result.regulation_home_goals,
                result.regulation_away_goals,
                kp.market,
                kp.selection
            FROM kellylab_picks kp
            LEFT JOIN LATERAL (
                SELECT r.result_classification, r.regulation_home_goals,
                       r.regulation_away_goals, r.first_acquired_at
                FROM fixture_result_observations r
                WHERE r.fixture_id = kp.fixture_id
                  AND r.first_acquired_at < %s
                  AND r.result_classification IN (
                      'PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE'
                  )
                ORDER BY r.first_acquired_at DESC, r.result_observation_id DESC
                LIMIT 1
            ) result ON TRUE
            WHERE kp.portfolio_id = %s
              AND kp.source_decision_at < %s
            ORDER BY kp.source_decision_at, kp.kelly_pick_id
            """,
            (cutoff, PORTFOLIO_ID, cutoff),
        )
        balance = int(starting_bankroll_minor)
        for row in PostgreSQLKellyLabRepository._row_dicts(cursor):
            outcome = row_outcome(row)
            value = pnl_minor(
                stake_minor=int(row["stake_minor"]),
                odds=row["odds"],
                outcome=outcome,
            )
            balance += int(value or 0)
        return max(1, balance)

    def sync_new_picks(self, *, now: datetime | None = None) -> dict[str, int]:
        materialized_at = (now or datetime.now(UTC)).astimezone(UTC)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT started_at, starting_bankroll_minor, flat_stake_minor,
                       kelly_fraction, max_bet_fraction, calibration_prior_n
                FROM kellylab_portfolios
                WHERE portfolio_id = %s
                """,
                (PORTFOLIO_ID,),
            )
            config_row = cursor.fetchone()
            if config_row is None:
                raise RuntimeError("KellyLab portfolio is not initialized")
            (
                started_at,
                starting_bankroll_minor,
                flat_stake_minor,
                kelly_fraction,
                max_bet_fraction,
                calibration_prior_n,
            ) = config_row

            candidates = self._candidate_rows(cursor, started_at=started_at)
            inserted = skipped_scope = 0
            for row in candidates:
                if is_universe_blocked_competition(
                    country=row.get("country"),
                    competition_name=row.get("competition_name"),
                    league_id=row.get("league_id"),
                    home_team=row.get("home_team"),
                    away_team=row.get("away_team"),
                ) or is_retired_research_segment(row):
                    skipped_scope += 1
                    continue

                decision_at = row["source_decision_at"]
                prior = self._prior_rows(cursor, cutoff=decision_at)
                calibration = calibration_snapshot(
                    row,
                    prior,
                    prior_n=int(calibration_prior_n),
                )
                bankroll_before = self._bankroll_before(
                    cursor,
                    cutoff=decision_at,
                    starting_bankroll_minor=int(starting_bankroll_minor),
                )
                plan = kelly_stake_plan(
                    bankroll_minor=bankroll_before,
                    odds=row["odds"],
                    probability=calibration["kelly_probability"],
                    kelly_fraction=Decimal(kelly_fraction),
                    max_bet_fraction=Decimal(max_bet_fraction),
                )
                kelly_pick_id = "kellylab-pick-v1:" + sha256(
                    f"{PORTFOLIO_ID}|{row['research_signal_id']}".encode()
                ).hexdigest()
                source_payload = {
                    "evaluation_id": row["evaluation_id"],
                    "model_version_id": row.get("model_version_id"),
                    "policy_config_fingerprint": row.get("policy_config_fingerprint"),
                    "late_materialization": materialized_at >= row["kickoff_at"],
                }
                cursor.execute(
                    """
                    INSERT INTO kellylab_picks (
                        kelly_pick_id, portfolio_id, research_signal_id, fixture_id,
                        source_decision_at, materialized_at, kickoff_at,
                        home_team, away_team, competition_name, country,
                        market, selection, bookmaker, odds,
                        model_probability, market_fair_probability, edge, expected_value,
                        probability_bucket, edge_bucket, odds_bucket,
                        calibration_snapshot, calibration_gap, kelly_probability,
                        raw_kelly_fraction, fractional_kelly_fraction,
                        applied_kelly_fraction, bankroll_before_minor, stake_minor,
                        flat_stake_minor, decision, contract_version, source_payload
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (research_signal_id) DO NOTHING
                    """,
                    (
                        kelly_pick_id,
                        PORTFOLIO_ID,
                        row["research_signal_id"],
                        row["fixture_id"],
                        decision_at,
                        materialized_at,
                        row["kickoff_at"],
                        row["home_team"],
                        row["away_team"],
                        row["competition_name"],
                        row["country"],
                        row["market"],
                        row["selection"],
                        row["bookmaker"],
                        row["odds"],
                        row["model_probability"],
                        row["market_fair_probability"],
                        row["edge"],
                        row["expected_value"],
                        probability_bucket(row["model_probability"]),
                        edge_bucket(row["edge"]),
                        odds_bucket(row["odds"]),
                        json.dumps(calibration, sort_keys=True),
                        calibration["combined_calibration_gap"],
                        calibration["kelly_probability"],
                        plan["raw_kelly_fraction"],
                        plan["fractional_kelly_fraction"],
                        plan["applied_kelly_fraction"],
                        bankroll_before,
                        plan["stake_minor"],
                        int(flat_stake_minor),
                        plan["decision"],
                        KELLYLAB_CONTRACT_VERSION,
                        json.dumps(source_payload, sort_keys=True),
                    ),
                )
                inserted += cursor.rowcount

        return {
            "candidates": len(candidates),
            "inserted": inserted,
            "skipped_scope": skipped_scope,
        }

    def portfolio_snapshot(self) -> dict[str, Any]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT portfolio_id, started_at, starting_bankroll_minor, flat_stake_minor,
                       kelly_fraction, max_bet_fraction, calibration_prior_n, currency
                FROM kellylab_portfolios
                WHERE portfolio_id = %s
                """,
                (PORTFOLIO_ID,),
            )
            config = cursor.fetchone()
            if config is None:
                raise RuntimeError("KellyLab portfolio is not initialized")
            config_keys = (
                "portfolio_id",
                "started_at",
                "starting_bankroll_minor",
                "flat_stake_minor",
                "kelly_fraction",
                "max_bet_fraction",
                "calibration_prior_n",
                "currency",
            )
            portfolio = dict(zip(config_keys, config, strict=True))

            cursor.execute(
                """
                SELECT
                    kp.*,
                    state.phase AS result_phase,
                    result.result_observation_id,
                    result.result_classification,
                    result.provider_status AS result_provider_status,
                    result.regulation_home_goals,
                    result.regulation_away_goals,
                    result.first_acquired_at AS result_first_acquired_at
                FROM kellylab_picks kp
                LEFT JOIN fixture_result_acquisition_states state
                    ON state.fixture_id = kp.fixture_id
                LEFT JOIN fixture_result_observations result
                    ON result.result_observation_id = state.current_observation_id
                WHERE kp.portfolio_id = %s
                ORDER BY kp.source_decision_at DESC, kp.kelly_pick_id DESC
                """,
                (PORTFOLIO_ID,),
            )
            rows = [dict(row) for row in self._row_dicts(cursor)]

        starting = int(portfolio["starting_bankroll_minor"])
        kelly_pnl_total = 0
        flat_pnl_total = 0
        for row in rows:
            outcome = row_outcome(row)
            row["outcome"] = outcome
            row["kelly_pnl_minor"] = pnl_minor(
                stake_minor=int(row["stake_minor"]),
                odds=row["odds"],
                outcome=outcome,
            )
            row["flat_pnl_minor"] = pnl_minor(
                stake_minor=int(row["flat_stake_minor"]),
                odds=row["odds"],
                outcome=outcome,
            )
            kelly_pnl_total += int(row["kelly_pnl_minor"] or 0)
            flat_pnl_total += int(row["flat_pnl_minor"] or 0)

        def drawdown(pnl_key: str) -> float:
            settled = sorted(
                (
                    row
                    for row in rows
                    if row["outcome"] in {"WIN", "LOSS", "VOID"}
                    and isinstance(row.get("result_first_acquired_at"), datetime)
                ),
                key=lambda row: (
                    row["result_first_acquired_at"],
                    row["kelly_pick_id"],
                ),
            )
            balance = peak = starting
            max_dd = 0.0
            for row in settled:
                balance += int(row[pnl_key] or 0)
                peak = max(peak, balance)
                if peak > 0:
                    max_dd = max(max_dd, (peak - balance) / peak)
            return max_dd

        settled_n = sum(row["outcome"] in {"WIN", "LOSS", "VOID"} for row in rows)
        active_n = sum(row["outcome"] == "PENDING" for row in rows)
        bet_n = sum(row["decision"] == "BET" for row in rows)
        no_bet_n = len(rows) - bet_n
        open_stake_minor = sum(
            int(row["stake_minor"])
            for row in rows
            if row["outcome"] == "PENDING" and row["decision"] == "BET"
        )
        portfolio.update(
            {
                "pick_count": len(rows),
                "bet_count": bet_n,
                "no_bet_count": no_bet_n,
                "settled_count": settled_n,
                "active_count": active_n,
                "open_stake_minor": open_stake_minor,
                "kelly_pnl_minor": kelly_pnl_total,
                "flat_pnl_minor": flat_pnl_total,
                "kelly_bankroll_minor": starting + kelly_pnl_total,
                "flat_bankroll_minor": starting + flat_pnl_total,
                "kelly_return_pct": (kelly_pnl_total / starting * 100) if starting else None,
                "flat_return_pct": (flat_pnl_total / starting * 100) if starting else None,
                "kelly_max_drawdown_pct": drawdown("kelly_pnl_minor") * 100,
                "flat_max_drawdown_pct": drawdown("flat_pnl_minor") * 100,
            }
        )
        return {"portfolio": portfolio, "picks": rows}
