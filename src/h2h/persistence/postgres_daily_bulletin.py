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
