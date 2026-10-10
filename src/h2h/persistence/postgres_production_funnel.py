"""Source-agnostic Production funnel persistence.

Production does not decide which bets are good. It clones already-formed picks from
research universes when they match the active intake contract, then owns only operational
state (PENDING/PLAYED/SKIPPED) and the shared exposure cap. When capacity is constrained,
approved buckets are consumed in the current ROI-priority order; EV and edge only break
ties inside the same ROI-ranked bucket.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from collections.abc import Callable
from typing import Any

from h2h.domain.competition_scope import is_universe_blocked_competition
from h2h.domain.operator_pick_state import OperatorPickState, OperatorPickStateEvent
from h2h.production_buckets import (
    BUCKET_PRIORITY as _BUCKET_PRIORITY,
    DEFAULT_BUCKET_IDS,
    KNOWN_BUCKET_IDS as _KNOWN_BUCKET_IDS,
    matching_bucket_ids,
    n_roi_priority_score,
)


ConnectionFactory = Callable[[], Any]


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _fact_id(prefix: str, value: str) -> str:
    return prefix + ":" + sha256(value.encode("utf-8")).hexdigest()


def active_bucket_ids(values: dict[str, str] | None = None) -> tuple[str, ...]:
    env = os.environ if values is None else values
    raw = env.get("QUANTBET_PRODUCTION_INTAKE_BUCKETS", "").strip()
    if not raw:
        return DEFAULT_BUCKET_IDS
    requested = tuple(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))
    unknown = tuple(item for item in requested if item not in _KNOWN_BUCKET_IDS)
    if unknown:
        raise ValueError("unknown production intake bucket(s): " + ", ".join(unknown))
    if not requested:
        raise ValueError("QUANTBET_PRODUCTION_INTAKE_BUCKETS must select at least one bucket")
    return tuple(sorted(requested, key=_BUCKET_PRIORITY.__getitem__))


def intake_contract_version(bucket_ids: tuple[str, ...]) -> str:
    canonical = ",".join(bucket_ids)
    return "PRODUCTION_FUNNEL_INTAKE_V3:" + sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProductionFunnelSyncResult:
    candidates_seen: int
    matched_candidates: int
    cloned_picks: int
    duplicate_candidates: int
    exposure_blocked: int
    open_exposure_minor: int
    intake_contract_version: str


class ProductionFunnelStateConflictError(ValueError):
    """An idempotency key contradicts an already persisted operator action."""


class ProductionFunnelExposureError(ValueError):
    """A state change would exceed the Production funnel exposure cap."""


class PostgreSQLProductionFunnelRepository:
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
        import psycopg

        return psycopg.connect(self._database_url)

    @staticmethod
    def _row_dicts(cursor: Any) -> tuple[dict[str, Any], ...]:
        columns = [item.name for item in cursor.description]
        return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())

    @staticmethod
    def _research_matches(row: dict[str, Any]) -> tuple[str, ...]:
        return matching_bucket_ids(row, source_universe="RESEARCH")

    @staticmethod
    def _goallab_matches(row: dict[str, Any]) -> tuple[str, ...]:
        return matching_bucket_ids(row, source_universe="GOALLAB")

    @staticmethod
    def _candidate_sort_key(
        priority: int,
        row: dict[str, Any],
    ) -> tuple[int, float, float, Any, str, str]:
        """Rank by current bucket N+ROI strength, then by pick EV and edge."""
        return (
            priority,
            -float(row["expected_value"]),
            -float(row["edge"]),
            row["source_decision_at"],
            str(row["source_universe"]),
            str(row["source_pick_id"]),
        )

    @staticmethod
    def _research_outcome(row: dict[str, Any]) -> str:
        if row.get("production_manual_void"):
            return "VOID"
        classification = row.get("result_classification")
        if classification == "NON_PLAYED_VOIDABLE":
            return "VOID"
        if classification != "PLAYED_SETTLEABLE":
            return "PENDING"
        home = row.get("regulation_home_goals")
        away = row.get("regulation_away_goals")
        if home is None or away is None:
            return "PENDING"
        total = int(home) + int(away)
        market = str(row.get("market_key") or "")
        selection = str(row.get("selection") or "")
        if market == "OU_25":
            won = total > 2 if selection == "OVER" else total <= 2
        elif market == "BTTS":
            both = int(home) > 0 and int(away) > 0
            won = both if selection == "YES" else not both
        else:
            return "PENDING"
        return "WIN" if won else "LOSS"

    @staticmethod
    def _research_performance_rows(cursor: Any) -> tuple[dict[str, Any], ...]:
        cursor.execute(
            """
            SELECT
                rs.fixture_id,
                e.market AS market_key,
                e.selected_selection AS selection,
                e.selected_odd AS odds,
                e.edge,
                e.expected_value,
                result.result_classification,
                result.regulation_home_goals,
                result.regulation_away_goals,
                (settlement.event_kind = 'MANUAL_VOID' AND settlement.outcome = 'VOID')
                    AS production_manual_void,
                latest.home_team,
                latest.away_team,
                latest.competition_name,
                latest.country,
                f.league_id
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
            LEFT JOIN fixture_result_acquisition_states state
                ON state.fixture_id = rs.fixture_id
            LEFT JOIN fixture_result_observations result
                ON result.result_observation_id = state.current_observation_id
            LEFT JOIN LATERAL (
                SELECT pse.event_kind, pse.outcome
                FROM pick_settlement_events pse
                WHERE pse.pick_id = rs.production_pick_id
                ORDER BY pse.occurred_at DESC, pse.settlement_event_id DESC
                LIMIT 1
            ) settlement ON TRUE
            WHERE rs.qualified_at IS NOT NULL
            """
        )
        return PostgreSQLProductionFunnelRepository._row_dicts(cursor)

    @staticmethod
    def _goallab_performance_rows(cursor: Any) -> tuple[dict[str, Any], ...]:
        cursor.execute(
            """
            SELECT
                p.fixture_id,
                p.market_key,
                p.selection,
                p.odds,
                p.edge,
                p.expected_value,
                p.expected_home_goals,
                p.expected_away_goals,
                p.stake_minor,
                s.outcome,
                s.pnl_minor,
                COALESCE(qlatest.home_team, platest.home_team) AS home_team,
                COALESCE(qlatest.away_team, platest.away_team) AS away_team,
                COALESCE(qlatest.competition_name, platest.competition_name) AS competition_name,
                COALESCE(qlatest.country, platest.country) AS country,
                f.league_id
            FROM quantlab_goal_picks p
            JOIN quantlab_goal_pick_settlements s ON s.goal_pick_id = p.goal_pick_id
            JOIN fixtures f ON f.fixture_id = p.fixture_id
            LEFT JOIN LATERAL (
                SELECT o.home_team, o.away_team, o.competition_name, o.country
                FROM quantlab_fixture_observations o
                WHERE o.fixture_id = p.fixture_id
                ORDER BY o.captured_at DESC, o.fixture_observation_id DESC
                LIMIT 1
            ) qlatest ON TRUE
            LEFT JOIN LATERAL (
                SELECT o.home_team, o.away_team, o.competition_name, o.country
                FROM fixture_observations o
                WHERE o.fixture_id = p.fixture_id
                ORDER BY o.observed_at DESC, o.fixture_observation_id DESC
                LIMIT 1
            ) platest ON TRUE
            """
        )
        return PostgreSQLProductionFunnelRepository._row_dicts(cursor)

    @classmethod
    def _bucket_performance(
        cls,
        cursor: Any,
        *,
        bucket_ids: tuple[str, ...],
    ) -> dict[str, dict[str, Any]]:
        accumulators = {
            bucket_id: {"graded_n": 0, "unit_pnl": 0.0}
            for bucket_id in bucket_ids
        }

        for row in cls._research_performance_rows(cursor):
            if is_universe_blocked_competition(
                country=row.get("country"),
                competition_name=row.get("competition_name"),
                league_id=row.get("league_id"),
                home_team=row.get("home_team"),
                away_team=row.get("away_team"),
            ):
                continue
            outcome = cls._research_outcome(row)
            if outcome not in {"WIN", "LOSS"}:
                continue
            unit_pnl = float(row["odds"]) - 1.0 if outcome == "WIN" else -1.0
            for bucket_id in matching_bucket_ids(row, source_universe="RESEARCH"):
                if bucket_id in accumulators:
                    accumulators[bucket_id]["graded_n"] += 1
                    accumulators[bucket_id]["unit_pnl"] += unit_pnl

        for row in cls._goallab_performance_rows(cursor):
            if is_universe_blocked_competition(
                country=row.get("country"),
                competition_name=row.get("competition_name"),
                league_id=row.get("league_id"),
                home_team=row.get("home_team"),
                away_team=row.get("away_team"),
            ):
                continue
            if str(row.get("outcome") or "") not in {"WIN", "LOSS"}:
                continue
            stake = int(row.get("stake_minor") or 0)
            if stake <= 0:
                continue
            unit_pnl = int(row.get("pnl_minor") or 0) / stake
            for bucket_id in matching_bucket_ids(row, source_universe="GOALLAB"):
                if bucket_id in accumulators:
                    accumulators[bucket_id]["graded_n"] += 1
                    accumulators[bucket_id]["unit_pnl"] += unit_pnl

        stats: dict[str, dict[str, Any]] = {}
        for bucket_id, accumulator in accumulators.items():
            graded_n = int(accumulator["graded_n"])
            roi_pct = (
                None
                if graded_n == 0
                else float(accumulator["unit_pnl"]) / graded_n * 100.0
            )
            stats[bucket_id] = {
                "graded_n": graded_n,
                "roi_pct": roi_pct,
                "priority_score": n_roi_priority_score(
                    graded_n=graded_n,
                    roi_pct=roi_pct,
                ),
            }
        return stats

    @staticmethod
    def _bucket_strength_key(
        bucket_id: str,
        stats: dict[str, dict[str, Any]],
    ) -> tuple[float, float, int, int, int]:
        item = stats[bucket_id]
        roi = item.get("roi_pct")
        return (
            float(item["priority_score"]),
            float("-inf") if roi is None else float(roi),
            min(int(item["graded_n"]), 100),
            int(item["graded_n"]),
            -_BUCKET_PRIORITY[bucket_id],
        )

    @staticmethod
    def _research_candidates(cursor: Any, *, now: datetime, fallback_stake_minor: int) -> tuple[dict[str, Any], ...]:
        cursor.execute(
            """
            SELECT
                'RESEARCH'::text AS source_universe,
                rs.research_signal_id AS source_pick_id,
                rs.fixture_id AS source_fixture_id,
                latest.home_team, latest.away_team, latest.competition_name, latest.country,
                latest.provider_status,
                e.market AS market_key, e.selected_selection AS selection,
                CASE WHEN e.market = 'OU_25' THEN 2.5::numeric ELSE NULL::numeric END AS line,
                e.bookmaker_id, e.bookmaker_key AS bookmaker_name, e.selected_odd AS odds,
                e.selected_devig_probability AS market_probability,
                e.model_probability, e.edge, e.expected_value,
                'Dixon-Coles'::text AS source_model_name,
                e.model_version_id AS source_model_version,
                rs.policy_config_fingerprint AS source_policy_version,
                e.quote_observed_at AS source_quote_observed_at,
                rs.qualified_at AS source_decision_at,
                latest.kickoff_at,
                COALESCE(
                    NULLIF(config.configuration->>'fixed_stake_minor', '')::bigint,
                    %s::bigint
                ) AS stake_minor,
                jsonb_build_object(
                    'research_signal_id', rs.research_signal_id,
                    'evaluation_id', rs.evaluation_id,
                    'block_reason', rs.block_reason,
                    'stage', rs.stage,
                    'source_stake_minor', COALESCE(
                        NULLIF(config.configuration->>'fixed_stake_minor', '')::bigint,
                        %s::bigint
                    )
                ) AS source_payload
            FROM research_signals rs
            JOIN value_evaluations e ON e.evaluation_id = rs.evaluation_id
            LEFT JOIN pick_policy_configurations config
                ON config.config_fingerprint = rs.policy_config_fingerprint
            JOIN LATERAL (
                SELECT fo.home_team, fo.away_team, fo.competition_name, fo.country,
                       fo.provider_status, fo.kickoff_at
                FROM fixture_observations fo
                WHERE fo.fixture_id = rs.fixture_id
                ORDER BY fo.observed_at DESC, fo.fixture_observation_id DESC
                LIMIT 1
            ) latest ON TRUE
            WHERE rs.qualified_at IS NOT NULL
              AND latest.kickoff_at > %s
              AND (
                    (
                        e.market = 'OU_25'
                        AND e.selected_selection IN ('UNDER', 'OVER')
                        AND e.selected_odd > 1.80 AND e.selected_odd <= 2.00
                    )
                    OR (
                        (
                            (e.market = 'OU_25' AND e.selected_selection = 'UNDER')
                            OR (e.market = 'BTTS' AND e.selected_selection = 'NO')
                        )
                        AND NOT (e.expected_value >= 0.30 OR e.edge >= 0.20)
                    )
                    OR (
                        e.market = 'OU_25' AND e.selected_selection = 'UNDER'
                        AND e.edge >= 0.10 AND e.edge < 0.15
                    )
                    OR (
                        e.market = 'OU_25' AND e.selected_selection = 'UNDER'
                        AND e.edge >= 0.20 AND e.edge < 0.30
                    )
                    OR (
                        e.market = 'BTTS' AND e.selected_selection = 'NO'
                        AND e.selected_odd > 2.00 AND e.selected_odd <= 2.50
                    )
              )
            ORDER BY rs.qualified_at ASC, rs.research_signal_id ASC
            LIMIT 5000
            """,
            (fallback_stake_minor, fallback_stake_minor, now),
        )
        return PostgreSQLProductionFunnelRepository._row_dicts(cursor)

    @staticmethod
    def _goallab_candidates(cursor: Any, *, now: datetime) -> tuple[dict[str, Any], ...]:
        cursor.execute(
            """
            SELECT
                'GOALLAB'::text AS source_universe,
                p.goal_pick_id AS source_pick_id,
                p.fixture_id AS source_fixture_id,
                COALESCE(qlatest.home_team, platest.home_team) AS home_team,
                COALESCE(qlatest.away_team, platest.away_team) AS away_team,
                COALESCE(qlatest.competition_name, platest.competition_name) AS competition_name,
                COALESCE(qlatest.country, platest.country) AS country,
                COALESCE(qlatest.provider_status, platest.provider_status, 'NS') AS provider_status,
                p.market_key, p.selection, p.line, p.bookmaker_id,
                p.bookmaker_name, p.odds, p.market_probability, p.model_probability,
                p.edge, p.expected_value, p.model_name AS source_model_name,
                p.model_version AS source_model_version,
                p.pick_policy_version AS source_policy_version,
                p.quote_observed_at AS source_quote_observed_at,
                p.decision_at AS source_decision_at,
                p.kickoff_at, p.stake_minor AS source_stake_minor,
                p.expected_home_goals, p.expected_away_goals,
                jsonb_build_object(
                    'goal_pick_id', p.goal_pick_id,
                    'source_decision_id', p.source_decision_id,
                    'feature_snapshot_id', p.feature_snapshot_id,
                    'expected_home_goals', p.expected_home_goals,
                    'expected_away_goals', p.expected_away_goals,
                    'source_stake_minor', p.stake_minor
                ) AS source_payload
            FROM quantlab_goal_picks p
            LEFT JOIN LATERAL (
                SELECT o.home_team, o.away_team, o.competition_name, o.country,
                       o.provider_status
                FROM quantlab_fixture_observations o
                WHERE o.fixture_id = p.fixture_id
                ORDER BY o.captured_at DESC, o.fixture_observation_id DESC
                LIMIT 1
            ) qlatest ON TRUE
            LEFT JOIN LATERAL (
                SELECT o.home_team, o.away_team, o.competition_name, o.country,
                       o.provider_status
                FROM fixture_observations o
                WHERE o.fixture_id = p.fixture_id
                ORDER BY o.observed_at DESC, o.fixture_observation_id DESC
                LIMIT 1
            ) platest ON TRUE
            WHERE p.kickoff_at > %s
              AND p.market_key = 'OU_25'
              AND p.selection = 'OVER'
              AND (
                    (
                        p.expected_home_goals + p.expected_away_goals >= 2.5
                        AND p.expected_home_goals + p.expected_away_goals < 3.0
                    )
                    OR (p.odds > 2.00 AND p.odds <= 2.50)
              )
            ORDER BY p.decision_at ASC, p.goal_pick_id ASC
            LIMIT 5000
            """,
            (now,),
        )
        return PostgreSQLProductionFunnelRepository._row_dicts(cursor)

    @staticmethod
    def _open_exposure(cursor: Any) -> int:
        cursor.execute(
            """
            WITH latest_state AS (
                SELECT DISTINCT ON (pick_id) pick_id, state
                FROM production_funnel_state_events
                ORDER BY pick_id, occurred_at DESC, persisted_at DESC, event_id DESC
            ),
            settlement AS (
                SELECT
                    p.pick_id,
                    CASE
                        WHEN p.source_universe = 'GOALLAB' THEN EXISTS (
                            SELECT 1 FROM quantlab_goal_pick_settlements s
                            WHERE s.goal_pick_id = p.source_pick_id
                        )
                        WHEN p.source_universe = 'RESEARCH' THEN EXISTS (
                            SELECT 1
                            FROM fixture_result_acquisition_states a
                            JOIN fixture_result_observations r
                              ON r.result_observation_id = a.current_observation_id
                            WHERE a.fixture_id = p.source_fixture_id
                              AND r.result_classification IN (
                                  'PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE'
                              )
                        )
                        ELSE FALSE
                    END AS settled
                FROM production_funnel_picks p
            )
            SELECT COALESCE(
                SUM(p.stake_minor) FILTER (
                    WHERE COALESCE(s.state, 'PENDING') <> 'SKIPPED'
                      AND NOT settlement.settled
                ),
                0
            )
            FROM production_funnel_picks p
            LEFT JOIN latest_state s ON s.pick_id = p.pick_id
            JOIN settlement ON settlement.pick_id = p.pick_id
            """
        )
        row = cursor.fetchone()
        return 0 if row is None else int(row[0])

    def exposure_breakdown(self) -> dict[str, int]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH latest_state AS (
                    SELECT DISTINCT ON (pick_id) pick_id, state
                    FROM production_funnel_state_events
                    ORDER BY pick_id, occurred_at DESC, persisted_at DESC, event_id DESC
                ),
                settled AS (
                    SELECT
                        p.pick_id,
                        CASE
                            WHEN p.source_universe = 'GOALLAB' THEN EXISTS (
                                SELECT 1 FROM quantlab_goal_pick_settlements s
                                WHERE s.goal_pick_id = p.source_pick_id
                            )
                            WHEN p.source_universe = 'RESEARCH' THEN EXISTS (
                                SELECT 1
                                FROM fixture_result_acquisition_states a
                                JOIN fixture_result_observations r
                                  ON r.result_observation_id = a.current_observation_id
                                WHERE a.fixture_id = p.source_fixture_id
                                  AND r.result_classification IN (
                                      'PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE'
                                  )
                            )
                            ELSE FALSE
                        END AS is_settled
                    FROM production_funnel_picks p
                )
                SELECT
                    COALESCE(SUM(p.stake_minor) FILTER (
                        WHERE COALESCE(s.state, 'PENDING') <> 'SKIPPED'
                          AND NOT settled.is_settled
                    ), 0),
                    COUNT(*) FILTER (
                        WHERE COALESCE(s.state, 'PENDING') = 'PENDING'
                          AND NOT settled.is_settled
                    ),
                    COUNT(*) FILTER (
                        WHERE s.state = 'PLAYED' AND NOT settled.is_settled
                    ),
                    COUNT(*) FILTER (WHERE s.state = 'SKIPPED'),
                    COUNT(*) FILTER (WHERE settled.is_settled)
                FROM production_funnel_picks p
                LEFT JOIN latest_state s ON s.pick_id = p.pick_id
                JOIN settled ON settled.pick_id = p.pick_id
                """
            )
            row = cursor.fetchone()
        if row is None:
            return {
                "open_exposure_minor": 0,
                "pending_count": 0,
                "played_open_count": 0,
                "skipped_count": 0,
                "settled_count": 0,
            }
        return {
            "open_exposure_minor": int(row[0]),
            "pending_count": int(row[1]),
            "played_open_count": int(row[2]),
            "skipped_count": int(row[3]),
            "settled_count": int(row[4]),
        }

    def sync(
        self,
        *,
        now: datetime,
        max_open_exposure_minor: int,
        currency: str,
        fallback_stake_minor: int,
        bucket_ids: tuple[str, ...] | None = None,
    ) -> ProductionFunnelSyncResult:
        cloned_at = _utc(now, "now")
        if isinstance(max_open_exposure_minor, bool) or max_open_exposure_minor <= 0:
            raise ValueError("max_open_exposure_minor must be positive")
        if isinstance(fallback_stake_minor, bool) or fallback_stake_minor <= 0:
            raise ValueError("fallback_stake_minor must be positive")
        requested = active_bucket_ids() if bucket_ids is None else bucket_ids
        if not requested or any(item not in _KNOWN_BUCKET_IDS for item in requested):
            raise ValueError("bucket_ids must contain known production intake buckets")
        selected = tuple(
            sorted(dict.fromkeys(requested), key=_BUCKET_PRIORITY.__getitem__)
        )
        contract = intake_contract_version(selected)
        allowed = frozenset(selected)

        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('production-funnel-sync-v1', 0))"
            )
            exposure = self._open_exposure(cursor)
            rows = list(
                self._research_candidates(
                    cursor,
                    now=cloned_at,
                    fallback_stake_minor=fallback_stake_minor,
                )
            )
            rows.extend(self._goallab_candidates(cursor, now=cloned_at))

            bucket_stats = self._bucket_performance(cursor, bucket_ids=selected)
            bucket_order = tuple(
                sorted(
                    selected,
                    key=lambda bucket_id: self._bucket_strength_key(bucket_id, bucket_stats),
                    reverse=True,
                )
            )
            dynamic_priority = {
                bucket_id: index
                for index, bucket_id in enumerate(bucket_order, 1)
            }

            matched: list[tuple[int, dict[str, Any], tuple[str, ...], str]] = []
            for row in rows:
                source = str(row["source_universe"])
                all_matches = (
                    self._research_matches(row)
                    if source == "RESEARCH"
                    else self._goallab_matches(row)
                )
                active_matches = tuple(
                    sorted(
                        (item for item in all_matches if item in allowed),
                        key=dynamic_priority.__getitem__,
                    )
                )
                if not active_matches:
                    continue
                primary_bucket_id = active_matches[0]
                priority = dynamic_priority[primary_bucket_id]
                matched.append((priority, row, active_matches, primary_bucket_id))

            matched.sort(key=lambda item: self._candidate_sort_key(item[0], item[1]))
            cloned = 0
            duplicates = 0
            blocked = 0
            for priority, row, matches, primary_bucket_id in matched:
                stake_minor = fallback_stake_minor
                if exposure + stake_minor > max_open_exposure_minor:
                    blocked += 1
                    continue
                pick_id = _fact_id(
                    "production-pick-v1",
                    f"{row['source_universe']}:{row['source_pick_id']}",
                )
                payload = row.get("source_payload")
                if isinstance(payload, str):
                    payload = json.loads(payload)
                payload = dict(payload or {})
                primary_stats = bucket_stats[primary_bucket_id]
                payload.update(
                    {
                        "production_primary_bucket_id": primary_bucket_id,
                        "production_bucket_graded_n": primary_stats["graded_n"],
                        "production_bucket_roi_pct": primary_stats["roi_pct"],
                        "production_bucket_priority_score": primary_stats["priority_score"],
                    }
                )
                cursor.execute(
                    """
                    INSERT INTO production_funnel_picks (
                        pick_id, source_universe, source_pick_id, source_fixture_id,
                        intake_contract_version, matched_bucket_ids, bucket_priority,
                        home_team, away_team, competition_name, country, provider_status,
                        market_key, selection, line, bookmaker_id, bookmaker_name, odds,
                        market_probability, model_probability, edge, expected_value,
                        source_model_name, source_model_version, source_policy_version,
                        source_quote_observed_at, source_decision_at, kickoff_at, cloned_at,
                        stake_minor, currency, source_payload
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s::jsonb
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        pick_id,
                        row["source_universe"],
                        row["source_pick_id"],
                        row["source_fixture_id"],
                        contract,
                        list(matches),
                        priority,
                        row["home_team"],
                        row["away_team"],
                        row["competition_name"],
                        row["country"],
                        row["provider_status"],
                        row["market_key"],
                        row["selection"],
                        row["line"],
                        row["bookmaker_id"],
                        row["bookmaker_name"],
                        row["odds"],
                        row["market_probability"],
                        row["model_probability"],
                        row["edge"],
                        row["expected_value"],
                        row["source_model_name"],
                        row["source_model_version"],
                        row["source_policy_version"],
                        row["source_quote_observed_at"],
                        row["source_decision_at"],
                        row["kickoff_at"],
                        cloned_at,
                        stake_minor,
                        currency,
                        json.dumps(payload, sort_keys=True, default=str),
                    ),
                )
                if cursor.rowcount == 1:
                    cloned += 1
                    exposure += stake_minor
                else:
                    duplicates += 1

        return ProductionFunnelSyncResult(
            candidates_seen=len(rows),
            matched_candidates=len(matched),
            cloned_picks=cloned,
            duplicate_candidates=duplicates,
            exposure_blocked=blocked,
            open_exposure_minor=exposure,
            intake_contract_version=contract,
        )


class PostgreSQLProductionFunnelStateRepository:
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
        import psycopg

        return psycopg.connect(self._database_url)

    @staticmethod
    def _event(row: tuple[Any, ...]) -> OperatorPickStateEvent:
        return OperatorPickStateEvent(
            row[0], row[1], OperatorPickState(row[2]), row[3], row[4]
        )

    @staticmethod
    def _is_settled(cursor: Any, pick_id: str) -> bool:
        cursor.execute(
            """
            SELECT CASE
                WHEN p.source_universe = 'GOALLAB' THEN EXISTS (
                    SELECT 1 FROM quantlab_goal_pick_settlements s
                    WHERE s.goal_pick_id = p.source_pick_id
                )
                WHEN p.source_universe = 'RESEARCH' THEN EXISTS (
                    SELECT 1
                    FROM fixture_result_acquisition_states a
                    JOIN fixture_result_observations r
                      ON r.result_observation_id = a.current_observation_id
                    WHERE a.fixture_id = p.source_fixture_id
                      AND r.result_classification IN (
                          'PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE'
                      )
                )
                ELSE FALSE
            END
            FROM production_funnel_picks p
            WHERE p.pick_id = %s
            """,
            (pick_id,),
        )
        row = cursor.fetchone()
        return bool(row and row[0])

    def set_state(
        self,
        pick_id: str,
        state: OperatorPickState,
        request_id: str,
        *,
        occurred_at: datetime,
        max_open_exposure_minor: int | None = None,
    ) -> OperatorPickStateEvent:
        if not isinstance(state, OperatorPickState):
            raise TypeError("state must be an OperatorPickState")
        if state is OperatorPickState.PENDING:
            raise ValueError("PENDING is derived before the first operator action")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        occurred = _utc(occurred_at, "occurred_at")
        request = request_id.strip()
        event_id = _fact_id("production-state-event-v1", request)

        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, pick_id, state, occurred_at, request_id "
                "FROM production_funnel_state_events WHERE request_id = %s",
                (request,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                event = self._event(existing)
                if event.pick_id != pick_id or event.state is not state:
                    raise ProductionFunnelStateConflictError(
                        "request_id already belongs to a different operator action"
                    )
                return event

            cursor.execute(
                "SELECT stake_minor FROM production_funnel_picks WHERE pick_id = %s FOR UPDATE",
                (pick_id,),
            )
            pick = cursor.fetchone()
            if pick is None:
                raise LookupError(f"production funnel pick {pick_id!r} does not exist")
            stake_minor = int(pick[0])

            cursor.execute(
                "SELECT state, occurred_at FROM production_funnel_state_events "
                "WHERE pick_id = %s "
                "ORDER BY occurred_at DESC, persisted_at DESC, event_id DESC LIMIT 1",
                (pick_id,),
            )
            latest = cursor.fetchone()
            effective_before = (
                OperatorPickState.PENDING if latest is None else OperatorPickState(latest[0])
            )
            becomes_latest = latest is None or occurred >= latest[1]
            effective_after = state if becomes_latest else effective_before

            if (
                effective_before is OperatorPickState.SKIPPED
                and effective_after is OperatorPickState.PLAYED
                and not self._is_settled(cursor, pick_id)
            ):
                if (
                    isinstance(max_open_exposure_minor, bool)
                    or not isinstance(max_open_exposure_minor, int)
                    or max_open_exposure_minor <= 0
                ):
                    raise ProductionFunnelExposureError(
                        "positive max_open_exposure_minor is required to reactivate a pick"
                    )
                open_exposure = PostgreSQLProductionFunnelRepository._open_exposure(cursor)
                if open_exposure + stake_minor > max_open_exposure_minor:
                    raise ProductionFunnelExposureError(
                        "PLAYED reactivation would exceed maximum Production exposure "
                        f"({open_exposure} + {stake_minor} > {max_open_exposure_minor})"
                    )

            cursor.execute(
                "INSERT INTO production_funnel_state_events "
                "(event_id, pick_id, state, occurred_at, request_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (event_id, pick_id, state.value, occurred, request),
            )
        return OperatorPickStateEvent(event_id, pick_id, state, occurred, request)

    def current_state(self, pick_id: str) -> OperatorPickState:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id FROM production_funnel_picks WHERE pick_id = %s",
                (pick_id,),
            )
            if cursor.fetchone() is None:
                raise LookupError(f"production funnel pick {pick_id!r} does not exist")
            cursor.execute(
                "SELECT state FROM production_funnel_state_events WHERE pick_id = %s "
                "ORDER BY occurred_at DESC, persisted_at DESC, event_id DESC LIMIT 1",
                (pick_id,),
            )
            row = cursor.fetchone()
        return OperatorPickState.PENDING if row is None else OperatorPickState(row[0])

    def history(self, pick_id: str) -> tuple[OperatorPickStateEvent, ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id FROM production_funnel_picks WHERE pick_id = %s",
                (pick_id,),
            )
            if cursor.fetchone() is None:
                raise LookupError(f"production funnel pick {pick_id!r} does not exist")
            cursor.execute(
                "SELECT event_id, pick_id, state, occurred_at, request_id "
                "FROM production_funnel_state_events WHERE pick_id = %s "
                "ORDER BY occurred_at, persisted_at, event_id",
                (pick_id,),
            )
            return tuple(self._event(row) for row in cursor.fetchall())

    def resolve_short_pick_id(self, short_id: str) -> str:
        if (
            not isinstance(short_id, str)
            or len(short_id) != 10
            or any(character not in "0123456789abcdef" for character in short_id.casefold())
        ):
            raise ValueError("short pick id must be exactly 10 hexadecimal characters")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id FROM production_funnel_picks WHERE RIGHT(pick_id, 10) = %s "
                "ORDER BY pick_id LIMIT 2",
                (short_id.casefold(),),
            )
            matches = tuple(row[0] for row in cursor.fetchall())
        if len(matches) != 1:
            raise LookupError(
                f"short pick id {short_id!r} resolved to {len(matches)} production picks"
            )
        return matches[0]
