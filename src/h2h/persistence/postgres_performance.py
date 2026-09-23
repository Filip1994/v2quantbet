"""PostgreSQL read models for realized financial and CLV performance."""

from __future__ import annotations

import os
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from h2h.read_models.performance import (
    BankrollCurvePoint,
    PerformanceGroup,
    PerformanceSummary,
    OperatorPerformanceSummary,
)


ConnectionFactory = Callable[[], Any]


class PostgreSQLPerformanceRepository:
    def __init__(
        self, database_url: str | None = None, *, connect: ConnectionFactory | None = None
    ) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")
        self._connect_factory = connect

    def connect(self):
        if self._connect_factory is not None:
            return self._connect_factory()
        import psycopg

        return psycopg.connect(self._database_url)

    @staticmethod
    def _effective_cte() -> str:
        return (
            "WITH effective AS (SELECT e.* FROM pick_settlement_events e "
            "WHERE NOT EXISTS (SELECT 1 FROM pick_settlement_events n "
            "WHERE n.prior_event_id = e.settlement_event_id)) "
        )

    def summary(self, bankroll_account_id: str) -> PerformanceSummary:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                self._effective_cte() + "SELECT a.currency, latest.balance_after_minor, "
                "COALESCE(SUM(r.stake_minor) FILTER (WHERE e.outcome IS NULL), 0), "
                "COALESCE(SUM(e.realized_pnl_minor) FILTER (WHERE e.outcome IS NOT NULL), 0), "
                "COALESCE(SUM(r.stake_minor) FILTER (WHERE e.outcome IS NOT NULL), 0), "
                "COALESCE(SUM(r.stake_minor) FILTER (WHERE e.outcome IN ('WIN','LOSS')), 0), "
                "COALESCE(SUM(r.stake_minor) FILTER (WHERE e.outcome = 'VOID'), 0), "
                "COUNT(*) FILTER (WHERE e.outcome = 'WIN'), "
                "COUNT(*) FILTER (WHERE e.outcome = 'LOSS'), "
                "COUNT(*) FILTER (WHERE e.outcome = 'VOID'), "
                "COUNT(*) FILTER (WHERE e.outcome IS NULL), "
                "COUNT(c.clv_fact_id), "
                "COUNT(c.clv_fact_id) FILTER (WHERE c.clv_ppm > 0), "
                "COUNT(c.clv_fact_id) FILTER (WHERE c.clv_ppm = 0), "
                "COUNT(c.clv_fact_id) FILTER (WHERE c.clv_ppm < 0), AVG(c.clv_ppm) "
                "FROM bankroll_accounts a JOIN LATERAL (SELECT balance_after_minor "
                "FROM bankroll_ledger_entries l WHERE l.bankroll_account_id = a.bankroll_account_id "
                "ORDER BY account_sequence DESC LIMIT 1) latest ON TRUE "
                "LEFT JOIN registered_picks r ON r.bankroll_account_id = a.bankroll_account_id "
                "LEFT JOIN effective e ON e.pick_id = r.pick_id "
                "LEFT JOIN pick_realized_clv c ON c.pick_id = r.pick_id "
                "WHERE a.bankroll_account_id = %s GROUP BY a.currency, latest.balance_after_minor",
                (bankroll_account_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"bankroll account {bankroll_account_id!r} does not exist")
            available, exposure = int(row[1]), int(row[2])
            graded = int(row[5])
            roi = None if graded == 0 else Decimal(int(row[3])) / Decimal(graded)
            curve = self.curve(bankroll_account_id)
            return PerformanceSummary(
                bankroll_account_id,
                row[0],
                available,
                exposure,
                available + exposure,
                int(row[3]),
                int(row[4]),
                graded,
                int(row[6]),
                exposure,
                roi,
                int(row[7]),
                int(row[8]),
                int(row[9]),
                int(row[10]),
                int(row[11]),
                int(row[12]),
                int(row[13]),
                int(row[14]),
                None if row[15] is None else Decimal(row[15]),
                curve,
            )

    def operator_summary(self, bankroll_account_id: str) -> OperatorPerformanceSummary:
        """Project actual finances from PLAYED picks without mutating the system ledger."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "WITH latest_operator AS ("
                "SELECT DISTINCT ON (pick_id) pick_id, state FROM pick_operator_state_events "
                "ORDER BY pick_id, occurred_at DESC, persisted_at DESC, event_id DESC), "
                "played_picks AS (SELECT r.* FROM registered_picks r "
                "LEFT JOIN latest_operator operator_state ON operator_state.pick_id = r.pick_id "
                "WHERE COALESCE(operator_state.state, 'PLAYED') = 'PLAYED'), "
                "effective AS (SELECT e.* FROM pick_settlement_events e WHERE NOT EXISTS ("
                "SELECT 1 FROM pick_settlement_events n "
                "WHERE n.prior_event_id = e.settlement_event_id)), "
                "initial AS (SELECT amount_minor FROM bankroll_ledger_entries "
                "WHERE bankroll_account_id = %s AND entry_type = 'INITIAL_BANKROLL' "
                "ORDER BY account_sequence LIMIT 1) "
                "SELECT a.currency, initial.amount_minor, "
                "COALESCE(SUM(r.stake_minor), 0), "
                "COALESCE(SUM(r.stake_minor) FILTER (WHERE e.outcome IS NULL), 0), "
                "COALESCE(SUM(r.stake_minor) FILTER (WHERE e.outcome IS NOT NULL), 0), "
                "COALESCE(SUM(e.gross_return_minor) FILTER (WHERE e.outcome IS NOT NULL), 0), "
                "COALESCE(SUM(e.realized_pnl_minor) FILTER (WHERE e.outcome IS NOT NULL), 0), "
                "COUNT(r.pick_id), COUNT(r.pick_id) FILTER (WHERE e.outcome IS NULL), "
                "COUNT(r.pick_id) FILTER (WHERE e.outcome = 'WIN'), "
                "COUNT(r.pick_id) FILTER (WHERE e.outcome = 'LOSS'), "
                "COUNT(r.pick_id) FILTER (WHERE e.outcome = 'VOID') "
                "FROM bankroll_accounts a CROSS JOIN initial "
                "LEFT JOIN played_picks r ON r.bankroll_account_id = a.bankroll_account_id "
                "LEFT JOIN effective e ON e.pick_id = r.pick_id "
                "WHERE a.bankroll_account_id = %s "
                "GROUP BY a.currency, initial.amount_minor",
                (bankroll_account_id, bankroll_account_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"bankroll account {bankroll_account_id!r} does not exist")
        initial = int(row[1])
        total_staked = int(row[2])
        pending = int(row[3])
        gross_returns = int(row[5])
        return OperatorPerformanceSummary(
            bankroll_account_id=bankroll_account_id,
            currency=row[0],
            initial_bankroll_minor=initial,
            available_bankroll_minor=initial - total_staked + gross_returns,
            open_exposure_minor=pending,
            total_staked_minor=total_staked,
            resolved_stake_minor=int(row[4]),
            gross_returns_minor=gross_returns,
            realized_pnl_minor=int(row[6]),
            pending_stake_minor=pending,
            played_count=int(row[7]),
            pending_count=int(row[8]),
            win_count=int(row[9]),
            loss_count=int(row[10]),
            void_count=int(row[11]),
        )

    def curve(self, bankroll_account_id: str) -> tuple[BankrollCurvePoint, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT l.account_sequence, l.occurred_at, l.entry_type, l.amount_minor, "
                "l.balance_after_minor, l.pick_id, r.stake_minor, e.event_kind, prior.event_kind "
                "FROM bankroll_ledger_entries l "
                "LEFT JOIN registered_picks r ON r.pick_id = l.pick_id "
                "LEFT JOIN pick_settlement_events e ON e.ledger_entry_id = l.ledger_entry_id "
                "LEFT JOIN pick_settlement_events prior ON prior.settlement_event_id = e.prior_event_id "
                "WHERE l.bankroll_account_id = %s ORDER BY l.account_sequence",
                (bankroll_account_id,),
            )
            exposure = 0
            points = []
            for (
                sequence,
                occurred,
                entry_type,
                _amount,
                balance,
                _pick,
                stake,
                kind,
                prior_kind,
            ) in cursor.fetchall():
                if entry_type == "STAKE_RESERVED":
                    exposure += int(stake)
                elif kind == "NORMAL":
                    exposure -= int(stake)
                elif kind == "REVERSAL":
                    exposure += int(stake)
                elif kind == "CORRECTION" and prior_kind == "REVERSAL":
                    exposure -= int(stake)
                points.append(
                    BankrollCurvePoint(
                        int(sequence), occurred, int(balance), exposure, int(balance) + exposure
                    )
                )
            return tuple(points)

    def groups(self, bankroll_account_id: str) -> tuple[PerformanceGroup, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                self._effective_cte()
                + "SELECT f.league_id, r.market, v.model_version_id, e.occurred_at::date, "
                "COUNT(*), COALESCE(SUM(r.stake_minor) FILTER "
                "(WHERE e.outcome IN ('WIN','LOSS')), 0), COALESCE(SUM(e.realized_pnl_minor), 0), "
                "AVG(c.clv_ppm) FROM effective e JOIN registered_picks r ON r.pick_id = e.pick_id "
                "JOIN fixtures f ON f.fixture_id = r.fixture_id "
                "JOIN value_evaluations v ON v.evaluation_id = r.evaluation_id "
                "LEFT JOIN pick_realized_clv c ON c.pick_id = r.pick_id "
                "WHERE r.bankroll_account_id = %s AND e.outcome IS NOT NULL "
                "GROUP BY f.league_id, r.market, v.model_version_id, e.occurred_at::date "
                "ORDER BY e.occurred_at::date, f.league_id, r.market, v.model_version_id",
                (bankroll_account_id,),
            )
            return tuple(
                PerformanceGroup(
                    int(row[0]),
                    row[1],
                    row[2],
                    row[3],
                    int(row[4]),
                    int(row[5]),
                    int(row[6]),
                    None if row[7] is None else Decimal(row[7]),
                )
                for row in cursor.fetchall()
            )
