"""Durable exposure-blocked research signals and read model."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from h2h.domain.registration_policy import RegistrationPolicyConfig


ConnectionFactory = Callable[[], Any]
RESEARCH_RESULT_METHOD_VERSION = "RESEARCH_RESULT_FINALIZATION_V1"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def research_signal_id(evaluation_id: str) -> str:
    prefix = "value-evaluation-v1:"
    if not isinstance(evaluation_id, str) or not evaluation_id.startswith(prefix):
        raise ValueError("evaluation_id must be a value-evaluation-v1 identifier")
    suffix = evaluation_id[len(prefix) :]
    if len(suffix) != 64:
        raise ValueError("evaluation_id digest must contain 64 hex characters")
    return "research-signal-v1:" + suffix


class PostgreSQLResearchSignalRepository:
    """Persist shadow signals without bankroll or registered-pick side effects."""

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

    def record_exposure_block(
        self,
        evaluation_id: str,
        *,
        blocked_at: datetime,
        blocked_stage: str,
        policy: RegistrationPolicyConfig,
    ) -> str:
        blocked = _utc(blocked_at, "blocked_at")
        if blocked_stage not in {"PRELIMINARY_RISK", "FINAL_RISK"}:
            raise ValueError("blocked_stage must be PRELIMINARY_RISK or FINAL_RISK")
        if not isinstance(policy, RegistrationPolicyConfig):
            raise TypeError("policy must be a RegistrationPolicyConfig")
        signal_id = research_signal_id(evaluation_id)
        configuration = json.dumps(
            policy.canonical_payload(), sort_keys=True, separators=(",", ":")
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id FROM value_evaluations WHERE evaluation_id = %s",
                (evaluation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f"value evaluation {evaluation_id!r} does not exist")
            fixture_id = str(row[0])
            cursor.execute(
                "INSERT INTO research_signals ("
                "signal_id, evaluation_id, fixture_id, blocked_at, blocked_stage, "
                "reason_codes, capture_method, policy_fingerprint, policy_configuration"
                ") VALUES (%s, %s, %s, %s, %s, %s, 'LIVE_V1', %s, %s::jsonb) "
                "ON CONFLICT DO NOTHING",
                (
                    signal_id,
                    evaluation_id,
                    fixture_id,
                    blocked,
                    blocked_stage,
                    ["MAX_OPEN_EXPOSURE_EXCEEDED"],
                    policy.fingerprint,
                    configuration,
                ),
            )
            cursor.execute(
                "SELECT evaluation_id, fixture_id, blocked_stage, reason_codes "
                "FROM research_signals WHERE signal_id = %s",
                (signal_id,),
            )
            stored = cursor.fetchone()
            if stored is None:
                raise RuntimeError("research signal insert did not resolve")
            if (
                stored[0] != evaluation_id
                or stored[1] != fixture_id
                or tuple(stored[3]) != ("MAX_OPEN_EXPOSURE_EXCEEDED",)
            ):
                raise RuntimeError("research signal identity conflicts")
        return signal_id

    def has_fixture(self, fixture_id: str) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM research_signals WHERE fixture_id = %s)",
                (fixture_id,),
            )
            return bool(cursor.fetchone()[0])

    def finalize_fixture_result(
        self,
        fixture_id: str,
        result_observation_id: str,
        *,
        finalized_at: datetime,
    ) -> bool:
        """Anchor one stable authoritative result for research-only analysis."""
        finalized = _utc(finalized_at, "finalized_at")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM research_signals WHERE fixture_id = %s)",
                (fixture_id,),
            )
            if not bool(cursor.fetchone()[0]):
                return False
            cursor.execute(
                "SELECT candidate_observation_id, candidate_first_seen_at, "
                "candidate_confirmation_count, last_checked_at "
                "FROM fixture_result_acquisition_states WHERE fixture_id = %s FOR UPDATE",
                (fixture_id,),
            )
            state = cursor.fetchone()
            if (
                state is None
                or state[0] != result_observation_id
                or int(state[2]) < 2
                or state[1] is None
                or state[3] is None
            ):
                raise RuntimeError("research result has not reached stable acquisition state")
            cursor.execute(
                "SELECT settlement_fingerprint FROM fixture_result_observations "
                "WHERE result_observation_id = %s AND fixture_id = %s",
                (result_observation_id, fixture_id),
            )
            result = cursor.fetchone()
            if result is None or result[0] is None:
                raise RuntimeError("research result lacks a settlement fingerprint")
            fingerprint = str(result[0])
            cursor.execute(
                "INSERT INTO research_fixture_result_finalizations ("
                "fixture_id, result_observation_id, settlement_fingerprint, finalized_at, "
                "method_version) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    fixture_id,
                    result_observation_id,
                    fingerprint,
                    finalized,
                    RESEARCH_RESULT_METHOD_VERSION,
                ),
            )
            cursor.execute(
                "SELECT result_observation_id, settlement_fingerprint "
                "FROM research_fixture_result_finalizations WHERE fixture_id = %s",
                (fixture_id,),
            )
            stored = cursor.fetchone()
            if stored is None:
                raise RuntimeError("research result finalization did not resolve")
            if stored[0] != result_observation_id or stored[1] != fingerprint:
                # Preserve the first stable result as immutable evidence. The acquisition
                # state exposes correction_required so analytics can exclude corrected cases.
                return True
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pick_settlement_events "
                "WHERE fixture_id = %s AND event_kind = 'NORMAL')",
                (fixture_id,),
            )
            has_pick_settlement = bool(cursor.fetchone()[0])
            if not has_pick_settlement:
                cursor.execute(
                    "UPDATE fixture_result_acquisition_states "
                    "SET phase = 'POST_SETTLEMENT_RECHECK', next_check_at = %s, "
                    "updated_at = %s, version = version + 1 "
                    "WHERE fixture_id = %s AND phase <> 'COMPLETE'",
                    (finalized + timedelta(hours=6), finalized, fixture_id),
                )
        return True

    def fixture_mapping(self, provider_fixture_id: str) -> dict[str, Any] | None:
        """Resolve a provider fixture ID to non-proprietary durable match metadata."""
        if not isinstance(provider_fixture_id, str) or not provider_fixture_id.isdigit():
            raise ValueError("provider_fixture_id must contain only digits")
        if int(provider_fixture_id) <= 0:
            raise ValueError("provider_fixture_id must be positive")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    f.provider_fixture_id,
                    f.fixture_id,
                    f.league_id,
                    f.season,
                    latest.home_team,
                    latest.away_team,
                    latest.competition_name,
                    latest.country,
                    latest.kickoff_at,
                    latest.provider_status
                FROM fixtures f
                JOIN LATERAL (
                    SELECT
                        fo.home_team,
                        fo.away_team,
                        fo.competition_name,
                        fo.country,
                        fo.kickoff_at,
                        fo.provider_status
                    FROM fixture_observations fo
                    WHERE fo.fixture_id = f.fixture_id
                    ORDER BY fo.observed_at DESC, fo.fixture_observation_id DESC
                    LIMIT 1
                ) latest ON TRUE
                WHERE f.provider = 'api-football'
                  AND f.provider_fixture_id = %s
                """,
                (provider_fixture_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        keys = (
            "provider_fixture_id",
            "fixture_id",
            "league_id",
            "season",
            "home_team",
            "away_team",
            "competition_name",
            "country",
            "kickoff_at",
            "provider_status",
        )
        return dict(zip(keys, row, strict=True))

    def rows(self, *, limit: int = 5000) -> tuple[dict[str, Any], ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH latest_fixture AS (
                    SELECT DISTINCT ON (fo.fixture_id)
                        fo.fixture_id,
                        fo.fixture_observation_id,
                        fo.home_team,
                        fo.away_team,
                        fo.competition_name,
                        fo.country,
                        fo.kickoff_at,
                        fo.provider_status
                    FROM fixture_observations fo
                    ORDER BY fo.fixture_id, fo.observed_at DESC, fo.fixture_observation_id DESC
                )
                SELECT
                    rs.signal_id,
                    rs.evaluation_id,
                    rs.fixture_id,
                    rs.blocked_at,
                    rs.blocked_stage,
                    rs.capture_method,
                    rs.policy_fingerprint,
                    f.provider_fixture_id,
                    f.league_id,
                    f.season,
                    lf.fixture_observation_id,
                    lf.home_team,
                    lf.away_team,
                    lf.competition_name,
                    lf.country,
                    lf.kickoff_at,
                    lf.provider_status,
                    e.bookmaker_id,
                    e.bookmaker_key,
                    e.market,
                    e.selected_selection,
                    e.selected_odd::text::numeric,
                    e.selected_devig_probability,
                    e.model_probability,
                    e.edge,
                    e.expected_value,
                    e.quote_observed_at,
                    e.selected_captured_at,
                    e.selected_series_id,
                    e.selected_snapshot_id,
                    e.source,
                    e.model_version_id,
                    close_q.snapshot_id,
                    close_q.odd::text::numeric,
                    close_q.observed_at,
                    close_q.captured_at,
                    rr.result_observation_id,
                    ro.result_classification,
                    ro.regulation_home_goals,
                    ro.regulation_away_goals,
                    COALESCE(state.correction_required, FALSE)
                FROM research_signals rs
                JOIN value_evaluations e ON e.evaluation_id = rs.evaluation_id
                JOIN fixtures f ON f.fixture_id = rs.fixture_id
                JOIN latest_fixture lf ON lf.fixture_id = rs.fixture_id
                LEFT JOIN LATERAL (
                    SELECT q.snapshot_id, q.odd, q.observed_at, q.captured_at
                    FROM quote_snapshots q
                    WHERE q.series_id = e.selected_series_id
                      AND q.source = e.source
                      AND q.observed_at <= lf.kickoff_at
                      AND q.captured_at <= lf.kickoff_at
                      AND q.captured_at >= e.selected_captured_at
                    ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC
                    LIMIT 1
                ) close_q ON TRUE
                LEFT JOIN research_fixture_result_finalizations rr
                    ON rr.fixture_id = rs.fixture_id
                LEFT JOIN fixture_result_observations ro
                    ON ro.result_observation_id = rr.result_observation_id
                    AND ro.fixture_id = rr.fixture_id
                LEFT JOIN fixture_result_acquisition_states state
                    ON state.fixture_id = rs.fixture_id
                ORDER BY rs.blocked_at DESC, rs.signal_id
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        keys = (
            "signal_id",
            "evaluation_id",
            "fixture_id",
            "blocked_at",
            "blocked_stage",
            "capture_method",
            "policy_fingerprint",
            "provider_fixture_id",
            "league_id",
            "season",
            "fixture_observation_id",
            "home_team",
            "away_team",
            "competition_name",
            "country",
            "kickoff_at",
            "provider_status",
            "bookmaker_id",
            "bookmaker_key",
            "market",
            "selection",
            "entry_odd",
            "market_fair_probability",
            "model_probability",
            "edge",
            "expected_value",
            "quote_observed_at",
            "quote_captured_at",
            "series_id",
            "entry_snapshot_id",
            "source",
            "model_version_id",
            "closing_snapshot_id",
            "closing_odd",
            "closing_observed_at",
            "closing_captured_at",
            "result_observation_id",
            "result_classification",
            "regulation_home_goals",
            "regulation_away_goals",
            "correction_required",
        )
        return tuple(dict(zip(keys, row, strict=True)) for row in rows)