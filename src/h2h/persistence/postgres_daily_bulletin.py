"""PostgreSQL Daily Bulletin projection over registered picks."""

from __future__ import annotations

from datetime import datetime

from h2h.persistence.postgres_pick_monitoring import PostgreSQLPickMonitoringRepository
from h2h.read_models.daily_bulletin import BulletinEntry


class PostgreSQLDailyBulletinRepository:
    def __init__(self, monitoring: PostgreSQLPickMonitoringRepository) -> None:
        self._monitoring = monitoring

    def entries_registered_between(
        self, *, start_at: datetime, end_at: datetime, as_of: datetime
    ) -> tuple[BulletinEntry, ...]:
        with self._monitoring.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.pick_id, r.decision_id, r.evaluation_id, r.fixture_id, "
                "latest.home_team, latest.away_team, latest.competition_name, "
                "latest.fixture_observation_id, latest.kickoff_at, "
                "registration.fixture_observation_id, registration.kickoff_at, "
                "r.market, r.selection, e.bookmaker_id, e.bookmaker_key, e.source, "
                "e.model_probability, e.selected_raw_implied_probability, "
                "e.selected_devig_probability, e.edge, e.expected_value, "
                "r.stake_minor, r.currency, e.model_version_id, r.config_fingerprint, "
                "r.registered_at "
                "FROM registered_picks r "
                "JOIN pick_decisions d ON d.decision_id = r.decision_id "
                "JOIN fixture_observations registration "
                "ON registration.fixture_observation_id = d.fixture_observation_id "
                "JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id "
                "JOIN LATERAL (SELECT f.fixture_observation_id, f.home_team, f.away_team, "
                "f.competition_name, f.kickoff_at FROM fixture_observations f "
                "WHERE f.fixture_id = r.fixture_id AND f.observed_at <= %s "
                "AND f.persisted_at <= %s ORDER BY f.observed_at DESC, "
                "f.fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "WHERE r.registered_at >= %s AND r.registered_at < %s "
                "ORDER BY r.registered_at, r.pick_id",
                (as_of, as_of, start_at, end_at),
            )
            rows = cursor.fetchall()
        return tuple(
            BulletinEntry(
                *row,
                odds=self._monitoring.read_lifecycle(row[0], as_of=as_of),
            )
            for row in rows
        )

