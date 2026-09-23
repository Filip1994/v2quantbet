"""Durable model-coverage inventory and historical acquisition cache."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from h2h.domain.competition_scope import CompetitionMetadata, classify_phase_i
from h2h.domain.model_coverage import ModelCoverageStatus, ProductionTrainingPolicy
from h2h.domain.model_lifecycle import DixonColesModelScope


ConnectionFactory = Callable[[], Any]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _scope_values(scope: DixonColesModelScope) -> tuple[object, ...]:
    return scope.provider, scope.team_id_namespace, scope.league_id, scope.season


@dataclass(frozen=True, slots=True)
class ModelCoverageRecord:
    scope: DixonColesModelScope
    status: ModelCoverageStatus
    first_required_at: datetime
    updated_at: datetime
    next_attempt_at: datetime | None
    attempt_count: int
    accepted_match_count: int | None
    fitted_match_count: int | None
    active_model_version_id: str | None
    active_generation: int | None


@dataclass(frozen=True, slots=True)
class CoverageCounts:
    total_eligible: int
    active: int
    missing: int
    training_required: int
    training_pending: int
    insufficient_data: int
    training_failed: int
    stale: int
    retrain_required: int


class PostgreSQLModelCoverageRepository:
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
        import psycopg

        return psycopg.connect(self._database_url)

    def refresh_inventory(self, policy: ProductionTrainingPolicy, *, now: datetime) -> int:
        """Discover required scopes from fixtures, independent of fixture failures."""
        current = _utc(now)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE model_coverage_scopes SET eligible = FALSE")
            cursor.execute(
                "SELECT DISTINCT ON (f.league_id, f.season) f.league_id, f.season, "
                "latest.country, latest.competition_name, latest.competition_type "
                "FROM fixtures f JOIN LATERAL (SELECT country, competition_name, "
                "competition_type, kickoff_at, observed_at, fixture_observation_id "
                "FROM fixture_observations o "
                "WHERE o.fixture_id = f.fixture_id ORDER BY observed_at DESC, "
                "fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "WHERE latest.kickoff_at > %s "
                "ORDER BY f.league_id, f.season, latest.observed_at DESC",
                (current,),
            )
            rows = cursor.fetchall()
            eligible = [
                (int(league_id), int(season))
                for league_id, season, country, name, competition_type in rows
                if classify_phase_i(
                    CompetitionMetadata(
                        country=country,
                        name=name,
                        type=competition_type,
                        level=None,
                    )
                ).eligible
            ]
            if eligible:
                cursor.execute(
                    "INSERT INTO model_coverage_scopes (provider, team_id_namespace, "
                    "league_id, season, status, first_required_at, updated_at, "
                    "next_attempt_at, policy_fingerprint, eligible) SELECT "
                    "'api-football', 'api-football', scope.league_id, scope.season, "
                    "'MISSING', %s, %s, %s, %s, TRUE FROM unnest(%s::bigint[], %s::integer[]) "
                    "AS scope(league_id, season) "
                    "ON CONFLICT (provider, team_id_namespace, league_id, season) DO UPDATE SET "
                    "updated_at = EXCLUDED.updated_at, eligible = TRUE",
                    (
                        current,
                        current,
                        current,
                        policy.fingerprint,
                        [league_id for league_id, _ in eligible],
                        [season for _, season in eligible],
                    ),
                )
            # Active pointers are authoritative. Fresh pointers remain ACTIVE; old ones
            # become STALE and are queued without deleting the current safe model.
            cursor.execute(
                "UPDATE model_coverage_scopes c SET status = CASE WHEN "
                "a.activated_at < %s THEN 'STALE' ELSE 'ACTIVE' END, "
                "active_model_version_id = a.model_version_id, active_generation = a.generation, "
                "next_attempt_at = CASE WHEN a.activated_at < %s THEN %s ELSE NULL END, "
                "updated_at = %s FROM dixon_coles_active_models a WHERE "
                "c.eligible AND a.provider = c.provider "
                "AND a.team_id_namespace = c.team_id_namespace "
                "AND a.league_id = c.league_id AND a.season = c.season",
                (
                    current - timedelta(days=policy.freshness_days),
                    current - timedelta(days=policy.freshness_days),
                    current,
                    current,
                ),
            )
            # Every newly observed missing scope is durably scheduled. Retry states keep
            # their explicit backoff, while policy changes force a safe retrain.
            cursor.execute(
                "UPDATE model_coverage_scopes SET status = CASE "
                "WHEN status = 'MISSING' THEN 'TRAINING_REQUIRED' "
                "WHEN policy_fingerprint <> %s AND status = 'ACTIVE' THEN 'RETRAIN_REQUIRED' "
                "ELSE status END, next_attempt_at = CASE WHEN status = 'MISSING' "
                "THEN %s ELSE next_attempt_at END, policy_fingerprint = %s, updated_at = %s "
                "WHERE eligible",
                (policy.fingerprint, current, policy.fingerprint, current),
            )
        return len(eligible)

    def recover_abandoned_claims(self, *, now: datetime, lease_seconds: float) -> int:
        if lease_seconds <= 0:
            raise ValueError("training claim lease must be positive")
        current = _utc(now)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE model_coverage_scopes SET status = 'TRAINING_REQUIRED', "
                "next_attempt_at = %s, updated_at = %s, last_error_class = "
                "'AbandonedTrainingClaim', last_error_message = "
                "'training claim recovered after process restart' WHERE status = "
                "'TRAINING_PENDING' AND training_started_at < %s RETURNING 1",
                (
                    current,
                    current,
                    current - timedelta(seconds=lease_seconds),
                ),
            )
            return len(cursor.fetchall())

    def claim_training_scopes(
        self, *, now: datetime, limit: int
    ) -> tuple[ModelCoverageRecord, ...]:
        if limit <= 0:
            raise ValueError("training scope limit must be positive")
        current = _utc(now)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "WITH selected AS (SELECT provider, team_id_namespace, league_id, season "
                "FROM model_coverage_scopes WHERE eligible AND status IN ('TRAINING_REQUIRED', "
                "'RETRAIN_REQUIRED', 'STALE', 'TRAINING_FAILED', 'INSUFFICIENT_DATA') "
                "AND (next_attempt_at IS NULL OR next_attempt_at <= %s) "
                "ORDER BY first_required_at, league_id, season FOR UPDATE SKIP LOCKED LIMIT %s) "
                "UPDATE model_coverage_scopes c SET status = 'TRAINING_PENDING', "
                "training_started_at = %s, updated_at = %s, attempt_count = attempt_count + 1, "
                "last_error_class = NULL, last_error_message = NULL FROM selected s WHERE "
                "(c.provider, c.team_id_namespace, c.league_id, c.season) = "
                "(s.provider, s.team_id_namespace, s.league_id, s.season) RETURNING "
                "c.provider, c.team_id_namespace, c.league_id, c.season, c.status, "
                "c.first_required_at, c.updated_at, c.next_attempt_at, c.attempt_count, "
                "c.accepted_match_count, c.fitted_match_count, c.active_model_version_id, "
                "c.active_generation",
                (current, limit, current, current),
            )
            return tuple(self._record(row) for row in cursor.fetchall())

    def required_team_ids(
        self, scope: DixonColesModelScope, *, now: datetime
    ) -> tuple[int, ...]:
        current = _utc(now)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT team_id FROM (SELECT f.provider_home_team_id AS team_id "
                "FROM fixtures f JOIN LATERAL (SELECT kickoff_at FROM fixture_observations o "
                "WHERE o.fixture_id = f.fixture_id ORDER BY observed_at DESC, "
                "fixture_observation_id DESC LIMIT 1) latest ON TRUE WHERE f.provider = %s "
                "AND f.league_id = %s AND f.season = %s AND latest.kickoff_at > %s UNION "
                "SELECT f.provider_away_team_id FROM fixtures f JOIN LATERAL "
                "(SELECT kickoff_at FROM fixture_observations o WHERE o.fixture_id = f.fixture_id "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "WHERE f.provider = %s AND f.league_id = %s AND f.season = %s "
                "AND latest.kickoff_at > %s) teams ORDER BY team_id",
                (
                    scope.provider,
                    scope.league_id,
                    scope.season,
                    current,
                    scope.provider,
                    scope.league_id,
                    scope.season,
                    current,
                ),
            )
            return tuple(int(row[0]) for row in cursor.fetchall())

    def mark_active(
        self,
        scope: DixonColesModelScope,
        *,
        model_version_id: str,
        generation: int,
        accepted_matches: int,
        fitted_matches: int,
        duration_seconds: float,
        now: datetime,
    ) -> None:
        self._finish(
            scope,
            status=ModelCoverageStatus.ACTIVE,
            now=now,
            next_attempt_at=None,
            accepted_matches=accepted_matches,
            fitted_matches=fitted_matches,
            duration_seconds=duration_seconds,
            model_version_id=model_version_id,
            generation=generation,
        )
        # Legacy fixture-level model-unavailable failures are obsolete once the
        # authoritative scope becomes active; removing them makes opportunity
        # processing resume on its next ordinary cadence without a restart.
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM production_item_failures p USING fixtures f WHERE "
                "p.worker_name = 'opportunity' AND p.item_id = f.fixture_id "
                "AND p.last_error_class = 'ActiveModelUnavailableError' "
                "AND f.provider = %s AND f.league_id = %s AND f.season = %s",
                (scope.provider, scope.league_id, scope.season),
            )

    def mark_insufficient(
        self,
        scope: DixonColesModelScope,
        error: BaseException,
        *,
        accepted_matches: int,
        duration_seconds: float,
        now: datetime,
        retry_after: timedelta = timedelta(days=1),
    ) -> None:
        self._finish(
            scope,
            status=ModelCoverageStatus.INSUFFICIENT_DATA,
            now=now,
            next_attempt_at=_utc(now) + retry_after,
            accepted_matches=accepted_matches,
            fitted_matches=None,
            duration_seconds=duration_seconds,
            error=error,
        )

    def mark_failed(
        self,
        scope: DixonColesModelScope,
        error: BaseException,
        *,
        duration_seconds: float,
        now: datetime,
        retry_after: timedelta = timedelta(hours=6),
    ) -> None:
        self._finish(
            scope,
            status=ModelCoverageStatus.TRAINING_FAILED,
            now=now,
            next_attempt_at=_utc(now) + retry_after,
            accepted_matches=None,
            fitted_matches=None,
            duration_seconds=duration_seconds,
            error=error,
        )

    def release_pending(
        self, scope: DixonColesModelScope, *, now: datetime, reason: str
    ) -> None:
        current = _utc(now)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE model_coverage_scopes SET status = 'TRAINING_REQUIRED', "
                "next_attempt_at = %s, updated_at = %s, last_error_class = %s, "
                "last_error_message = %s WHERE provider = %s AND team_id_namespace = %s "
                "AND league_id = %s AND season = %s AND status = 'TRAINING_PENDING'",
                (
                    current,
                    current,
                    "TrainingInterrupted",
                    reason[:500],
                    *_scope_values(scope),
                ),
            )

    def _finish(
        self,
        scope: DixonColesModelScope,
        *,
        status: ModelCoverageStatus,
        now: datetime,
        next_attempt_at: datetime | None,
        accepted_matches: int | None,
        fitted_matches: int | None,
        duration_seconds: float,
        model_version_id: str | None = None,
        generation: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        current = _utc(now)
        error_class = None if error is None else type(error).__name__[:100]
        error_message = None if error is None else " ".join(str(error).split())[:500]
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE model_coverage_scopes SET status = %s, updated_at = %s, "
                "training_finished_at = %s, next_attempt_at = %s, accepted_match_count = %s, "
                "fitted_match_count = %s, last_training_duration_seconds = %s, "
                "last_error_class = %s, last_error_message = %s, "
                "active_model_version_id = COALESCE(%s, active_model_version_id), "
                "active_generation = COALESCE(%s, active_generation) WHERE provider = %s "
                "AND team_id_namespace = %s AND league_id = %s AND season = %s",
                (
                    status.value,
                    current,
                    current,
                    next_attempt_at,
                    accepted_matches,
                    fitted_matches,
                    duration_seconds,
                    error_class,
                    error_message,
                    model_version_id,
                    generation,
                    *_scope_values(scope),
                ),
            )

    def status(self, scope: DixonColesModelScope) -> ModelCoverageStatus | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM model_coverage_scopes WHERE provider = %s AND "
                "team_id_namespace = %s AND league_id = %s AND season = %s",
                _scope_values(scope),
            )
            row = cursor.fetchone()
            return None if row is None else ModelCoverageStatus(row[0])

    def opportunity_status(self, scope: DixonColesModelScope) -> str | None:
        """Return ACTIVE while a safe pointer remains available during retraining."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT status, active_model_version_id FROM model_coverage_scopes WHERE "
                "provider = %s AND team_id_namespace = %s AND league_id = %s AND season = %s",
                _scope_values(scope),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return ModelCoverageStatus.ACTIVE.value if row[1] is not None else row[0]

    def has_pending(self, *, now: datetime) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM model_coverage_scopes WHERE eligible AND status IN "
                "('TRAINING_REQUIRED', 'RETRAIN_REQUIRED', 'STALE', 'TRAINING_FAILED', "
                "'INSUFFICIENT_DATA') AND (next_attempt_at IS NULL OR next_attempt_at <= %s))",
                (_utc(now),),
            )
            return bool(cursor.fetchone()[0])

    def coverage_counts(self) -> CoverageCounts:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'ACTIVE'), "
                "COUNT(*) FILTER (WHERE status = 'MISSING'), "
                "COUNT(*) FILTER (WHERE status = 'TRAINING_REQUIRED'), "
                "COUNT(*) FILTER (WHERE status = 'TRAINING_PENDING'), "
                "COUNT(*) FILTER (WHERE status = 'INSUFFICIENT_DATA'), "
                "COUNT(*) FILTER (WHERE status = 'TRAINING_FAILED'), "
                "COUNT(*) FILTER (WHERE status = 'STALE'), "
                "COUNT(*) FILTER (WHERE status = 'RETRAIN_REQUIRED') "
                "FROM model_coverage_scopes WHERE eligible"
            )
            return CoverageCounts(*(int(value) for value in cursor.fetchone()))

    def load_acquisition(
        self, *, league_id: int, season: int, start_at: datetime, end_at: datetime
    ) -> Mapping[str, Any] | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT response_payload FROM model_training_acquisitions WHERE provider = "
                "'api-football' AND league_id = %s AND season = %s AND training_start_at = %s "
                "AND training_end_at = %s AND status = 'COMPLETE'",
                (league_id, season, _utc(start_at), _utc(end_at)),
            )
            row = cursor.fetchone()
            return None if row is None else row[0]

    def save_acquisition(
        self,
        *,
        league_id: int,
        season: int,
        start_at: datetime,
        end_at: datetime,
        payload: Mapping[str, Any],
        accepted_match_count: int,
        acquired_at: datetime,
    ) -> None:
        from psycopg.types.json import Jsonb

        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO model_training_acquisitions (provider, league_id, season, "
                "training_start_at, training_end_at, status, response_payload, "
                "accepted_match_count, acquired_at) VALUES ('api-football', %s, %s, %s, %s, "
                "'COMPLETE', %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    league_id,
                    season,
                    _utc(start_at),
                    _utc(end_at),
                    Jsonb(dict(payload)),
                    accepted_match_count,
                    _utc(acquired_at),
                ),
            )

    @staticmethod
    def _record(row: tuple[Any, ...]) -> ModelCoverageRecord:
        return ModelCoverageRecord(
            scope=DixonColesModelScope(row[0], row[1], int(row[2]), int(row[3])),
            status=ModelCoverageStatus(row[4]),
            first_required_at=row[5],
            updated_at=row[6],
            next_attempt_at=row[7],
            attempt_count=int(row[8]),
            accepted_match_count=row[9],
            fitted_match_count=row[10],
            active_model_version_id=row[11],
            active_generation=row[12],
        )
