"""PostgreSQL Daily Bulletin projection over registered picks."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

from h2h.persistence.postgres_pick_monitoring import PostgreSQLPickMonitoringRepository
from h2h.read_models.daily_bulletin import BulletinEntry, DailyBulletinSnapshot


class PostgreSQLDailyBulletinRepository:
    def __init__(self, monitoring: PostgreSQLPickMonitoringRepository) -> None:
        self._monitoring = monitoring

    def actionable_entries(
        self, *, start_at: datetime, end_at: datetime, as_of: datetime
    ) -> tuple[BulletinEntry, ...]:
        with self._monitoring.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.pick_id, r.decision_id, r.evaluation_id, r.fixture_id, "
                "latest.home_team, latest.away_team, latest.competition_name, "
                "latest.fixture_observation_id, latest.kickoff_at, "
                "registration.fixture_observation_id, registration.kickoff_at, "
                "r.market, r.selection, e.bookmaker_id, e.bookmaker_key, e.source, "
                "e.selected_odd, (1 + (policy.configuration->>'minimum_expected_value')::numeric) "
                "/ e.model_probability, "
                "e.model_probability, e.selected_raw_implied_probability, "
                "e.selected_devig_probability, e.edge, e.expected_value, "
                "r.stake_minor, r.currency, e.model_version_id, r.config_fingerprint, "
                "r.registered_at "
                "FROM registered_picks r "
                "JOIN pick_decisions d ON d.decision_id = r.decision_id "
                "JOIN pick_policy_configurations policy "
                "ON policy.config_fingerprint = r.config_fingerprint "
                "JOIN fixture_observations registration "
                "ON registration.fixture_observation_id = d.fixture_observation_id "
                "JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id "
                "JOIN LATERAL (SELECT f.fixture_observation_id, f.home_team, f.away_team, "
                "f.competition_name, f.kickoff_at, f.provider_status FROM fixture_observations f "
                "WHERE f.fixture_id = r.fixture_id AND f.observed_at <= %s "
                "AND f.persisted_at <= %s ORDER BY f.observed_at DESC, "
                "f.fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "WHERE latest.kickoff_at > %s AND latest.kickoff_at <= %s "
                "AND latest.provider_status = 'NS' "
                "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events settled "
                "WHERE settled.pick_id = r.pick_id AND settled.outcome IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM pick_settlement_events successor "
                "WHERE successor.prior_event_id = settled.settlement_event_id)) "
                "ORDER BY r.registered_at, r.pick_id",
                (as_of, as_of, start_at, end_at),
            )
            rows = cursor.fetchall()
            result_rows = {}
            for row in rows:
                cursor.execute(
                    "SELECT ro.provider_status, ro.result_observation_id, effective.outcome, "
                    "effective.gross_return_minor, effective.realized_pnl_minor, c.clv_ppm, "
                    "f.outcome, f.cutoff_at, used.provider_kickoff_at "
                    "FROM registered_picks r "
                    "LEFT JOIN fixture_result_acquisition_states s ON s.fixture_id = r.fixture_id "
                    "LEFT JOIN fixture_result_observations ro "
                    "ON ro.result_observation_id = s.current_observation_id "
                    "LEFT JOIN LATERAL (SELECT e.* FROM pick_settlement_events e "
                    "WHERE e.pick_id = r.pick_id AND NOT EXISTS (SELECT 1 FROM "
                    "pick_settlement_events n WHERE n.prior_event_id = e.settlement_event_id) "
                    "LIMIT 1) effective ON TRUE "
                    "LEFT JOIN fixture_result_observations used "
                    "ON used.result_observation_id = effective.result_observation_id "
                    "LEFT JOIN pick_realized_clv c ON c.pick_id = r.pick_id "
                    "LEFT JOIN pick_closing_finalizations f ON f.pick_id = r.pick_id "
                    "WHERE r.pick_id = %s",
                    (row[0],),
                )
                result_rows[row[0]] = cursor.fetchone()
        entries = []
        for row in rows:
            financial = result_rows[row[0]]
            status = "PENDING_SETTLEMENT"
            if financial[5] is not None:
                status = "AVAILABLE"
            elif financial[2] is not None:
                if financial[6] in (None, "NO_VALID_QUOTE"):
                    status = "NO_VALID_CLOSING"
                elif financial[6] == "STALE_QUOTE":
                    status = "STALE_CLOSING"
                elif financial[7] != financial[8]:
                    status = "KICKOFF_CHANGED_AFTER_CLOSING"
                else:
                    status = "PROVENANCE_CONFLICT"
            entries.append(
                BulletinEntry(
                    *row,
                    odds=self._monitoring.read_lifecycle(row[0], as_of=as_of),
                    result_status=financial[0],
                    result_observation_id=financial[1],
                    settlement_outcome=financial[2],
                    gross_return_minor=None if financial[3] is None else int(financial[3]),
                    realized_pnl_minor=None if financial[4] is None else int(financial[4]),
                    realized_clv_status=status,
                    realized_clv_ppm=None if financial[5] is None else int(financial[5]),
                )
            )
        return tuple(entries)

    def create_snapshot(
        self,
        *,
        local_date: date,
        timezone: str,
        as_of: datetime,
        horizon: timedelta,
        entries: tuple[BulletinEntry, ...],
    ) -> DailyBulletinSnapshot:
        version = "DAILY_BULLETIN_V1"
        semantic = f"{version}|{timezone}|{local_date.isoformat()}"
        bulletin_id = "daily-bulletin-v1:" + sha256(semantic.encode()).hexdigest()
        current = as_of.astimezone(UTC)
        horizon_seconds = int(horizon.total_seconds())
        with self._monitoring.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (bulletin_id,))
            cursor.execute(
                "INSERT INTO daily_bulletins (bulletin_id, bulletin_version, local_date, "
                "timezone, generated_at, as_of, horizon_seconds) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    bulletin_id,
                    version,
                    local_date,
                    timezone,
                    current,
                    current,
                    horizon_seconds,
                ),
            )
            inserted = cursor.rowcount == 1
            if inserted:
                for ordinal, entry in enumerate(entries, start=1):
                    cursor.execute(
                        "INSERT INTO daily_bulletin_memberships "
                        "(bulletin_id, pick_id, ordinal, fixture_kickoff_at, "
                        "actionable_status) VALUES (%s, %s, %s, %s, 'ACTIONABLE')",
                        (bulletin_id, entry.pick_id, ordinal, entry.current_kickoff_at),
                    )
            cursor.execute(
                "SELECT bulletin_version, local_date, timezone, generated_at, as_of, "
                "horizon_seconds FROM daily_bulletins WHERE bulletin_id = %s",
                (bulletin_id,),
            )
            row = cursor.fetchone()
            cursor.execute(
                "SELECT pick_id FROM daily_bulletin_memberships WHERE bulletin_id = %s "
                "ORDER BY ordinal",
                (bulletin_id,),
            )
            pick_ids = tuple(value[0] for value in cursor.fetchall())
        return DailyBulletinSnapshot(
            bulletin_id,
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            int(row[5]),
            pick_ids,
            inserted,
        )
