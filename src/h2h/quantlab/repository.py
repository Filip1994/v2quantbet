"""Persistence boundary for QuantLab-owned market/context state and shadow reads."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _identifier(prefix: str, payload: dict[str, Any]) -> str:
    return prefix + sha256(_json(payload).encode()).hexdigest()


def _row_dicts(cursor: Any) -> tuple[dict[str, Any], ...]:
    columns = tuple(item.name for item in cursor.description)
    return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


class PostgreSQLQuantLabRepository:
    """Reads shared immutable football facts; writes only quantlab_* state."""

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
        required = (
            "quantlab_shadow_bets",
            "quantlab_fixtures",
            "quantlab_fixture_observations",
            "quantlab_fixture_discovery_shards",
            "quantlab_market_observations",
            "quantlab_fixture_context_observations",
            "quantlab_match_statistics_observations",
            "quantlab_standings_snapshots",
            "quantlab_card_feature_snapshots",
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname FROM pg_class WHERE relname = ANY(%s)",
                (list(required),),
            )
            found = {row[0] for row in cursor.fetchall()}
            return found == set(required)

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
                "q.settled_at, COALESCE(qlatest.home_team, platest.home_team) AS home_team, "
                "COALESCE(qlatest.away_team, platest.away_team) AS away_team, "
                "COALESCE(qlatest.competition_name, platest.competition_name) AS competition_name, "
                "COALESCE(qlatest.country, platest.country) AS country, "
                "COALESCE(qlatest.kickoff_at, platest.kickoff_at) AS kickoff_at "
                "FROM quantlab_shadow_bets q "
                "LEFT JOIN LATERAL ("
                " SELECT home_team, away_team, competition_name, country, kickoff_at "
                " FROM quantlab_fixture_observations o WHERE o.fixture_id = q.fixture_id "
                " ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
                ") qlatest ON TRUE "
                "LEFT JOIN LATERAL ("
                " SELECT home_team, away_team, competition_name, country, kickoff_at "
                " FROM fixture_observations o WHERE o.fixture_id = q.fixture_id "
                " ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
                ") platest ON TRUE "
                "WHERE q.lab = %s ORDER BY q.decision_at DESC, q.shadow_bet_id DESC LIMIT %s",
                (lab, limit),
            )
            return _row_dicts(cursor)

    def upcoming_fixtures(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        limit: int = 250,
    ) -> tuple[dict[str, Any], ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT f.fixture_id, f.provider_fixture_id, latest.league_id, latest.season, "
                "latest.home_team_id, latest.away_team_id, latest.home_team, latest.away_team, "
                "latest.competition_name, latest.country, latest.competition_type, "
                "latest.kickoff_at, latest.provider_status "
                "FROM quantlab_fixtures f "
                "JOIN LATERAL ("
                " SELECT league_id, season, home_team_id, away_team_id, home_team, away_team, "
                "        competition_name, country, competition_type, kickoff_at, provider_status "
                " FROM quantlab_fixture_observations o WHERE o.fixture_id = f.fixture_id "
                " ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
                ") latest ON TRUE "
                "WHERE latest.kickoff_at >= %s AND latest.kickoff_at < %s "
                "ORDER BY latest.kickoff_at, f.fixture_id LIMIT %s",
                (start_at, end_at, limit),
            )
            return _row_dicts(cursor)

    def fixture_discovery_due(
        self,
        fixture_date: date,
        *,
        now: datetime,
        refresh_seconds: int,
    ) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(captured_at) FROM quantlab_fixture_discovery_shards "
                "WHERE fixture_date = %s",
                (fixture_date,),
            )
            row = cursor.fetchone()
        last = None if row is None else row[0]
        return last is None or last <= now - timedelta(seconds=refresh_seconds)

    def save_fixture_discovery(
        self,
        *,
        fixture_date: date,
        captured_at: datetime,
        observations: Iterable[Any],
    ) -> int:
        rows = tuple(observations)
        shard_id = _identifier(
            "quantlab-fixture-shard-v1:",
            {
                "fixture_date": fixture_date.isoformat(),
                "captured_at": captured_at.isoformat(),
                "fixture_count": len(rows),
            },
        )
        with self.connect() as connection, connection.cursor() as cursor:
            for item in rows:
                fixture = item.fixture
                provider_fixture_id = int(fixture.provider_fixture_id or "")
                cursor.execute(
                    "INSERT INTO quantlab_fixtures "
                    "(fixture_id, provider_fixture_id, first_seen_at) VALUES (%s, %s, %s) "
                    "ON CONFLICT (fixture_id) DO NOTHING",
                    (fixture.fixture_id, provider_fixture_id, captured_at),
                )
                cursor.execute(
                    "INSERT INTO quantlab_fixture_observations ("
                    "fixture_observation_id, fixture_id, provider_fixture_id, league_id, season, "
                    "home_team_id, away_team_id, home_team, away_team, competition_name, country, "
                    "competition_type, kickoff_at, provider_status, captured_at, raw_payload"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    (
                        item.fixture_observation_id,
                        fixture.fixture_id,
                        provider_fixture_id,
                        fixture.competition_id,
                        fixture.season,
                        fixture.provider_home_team_id,
                        fixture.provider_away_team_id,
                        fixture.home_team,
                        fixture.away_team,
                        fixture.competition_name,
                        fixture.country,
                        fixture.competition_type,
                        fixture.kickoff_at,
                        fixture.status,
                        item.captured_at,
                        _json(item.raw_payload),
                    ),
                )
            cursor.execute(
                "INSERT INTO quantlab_fixture_discovery_shards "
                "(discovery_shard_id, fixture_date, captured_at, fixture_count) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (shard_id, fixture_date, captured_at, len(rows)),
            )
        return len(rows)

    def completed_for_context_backfill(
        self, *, before: datetime, limit: int = 80
    ) -> tuple[dict[str, Any], ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT f.fixture_id, f.provider_fixture_id::BIGINT AS provider_fixture_id, "
                "f.league_id, f.season, f.provider_home_team_id AS home_team_id, "
                "f.provider_away_team_id AS away_team_id, latest.home_team, latest.away_team, "
                "latest.competition_name, latest.country, latest.competition_type, "
                "latest.kickoff_at, result.provider_status "
                "FROM fixtures f "
                "JOIN LATERAL ("
                "  SELECT home_team, away_team, competition_name, country, competition_type, kickoff_at "
                "  FROM fixture_observations o WHERE o.fixture_id = f.fixture_id "
                "  ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1"
                ") latest ON TRUE "
                "JOIN LATERAL ("
                "  SELECT provider_status, result_classification "
                "  FROM fixture_result_observations r WHERE r.fixture_id = f.fixture_id "
                "  ORDER BY first_acquired_at DESC, result_observation_id DESC LIMIT 1"
                ") result ON TRUE "
                "WHERE latest.kickoff_at < %s "
                "AND result.result_classification = 'PLAYED_SETTLEABLE' "
                "AND NOT EXISTS (SELECT 1 FROM quantlab_match_statistics_observations s "
                "                WHERE s.fixture_id = f.fixture_id) "
                "ORDER BY latest.kickoff_at DESC LIMIT %s",
                (before, limit),
            )
            production = _row_dicts(cursor)
            cursor.execute(
                "SELECT f.fixture_id, f.provider_fixture_id, latest.league_id, latest.season, "
                "latest.home_team_id, latest.away_team_id, latest.home_team, latest.away_team, "
                "latest.competition_name, latest.country, latest.competition_type, "
                "latest.kickoff_at, latest.provider_status "
                "FROM quantlab_fixtures f "
                "JOIN LATERAL ("
                " SELECT league_id, season, home_team_id, away_team_id, home_team, away_team, "
                "        competition_name, country, competition_type, kickoff_at, provider_status "
                " FROM quantlab_fixture_observations o WHERE o.fixture_id = f.fixture_id "
                " ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
                ") latest ON TRUE "
                "WHERE latest.kickoff_at < %s "
                "AND latest.provider_status IN ('FT', 'AET', 'PEN') "
                "AND NOT EXISTS (SELECT 1 FROM quantlab_match_statistics_observations s "
                "                WHERE s.fixture_id = f.fixture_id) "
                "ORDER BY latest.kickoff_at DESC LIMIT %s",
                (before, limit),
            )
            discovered = _row_dicts(cursor)

        by_fixture = {str(item["fixture_id"]): item for item in production}
        for item in discovered:
            by_fixture[str(item["fixture_id"])] = item
        ordered = sorted(
            by_fixture.values(),
            key=lambda item: (item["kickoff_at"], str(item["fixture_id"])),
            reverse=True,
        )
        return tuple(ordered[:limit])

    def market_capture_due(
        self, fixture_id: str, *, now: datetime, refresh_seconds: int
    ) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(captured_at) FROM quantlab_market_observations WHERE fixture_id = %s",
                (fixture_id,),
            )
            row = cursor.fetchone()
        last = None if row is None else row[0]
        return last is None or last <= now - timedelta(seconds=refresh_seconds)

    def context_due(
        self, fixture_id: str, *, now: datetime, refresh_seconds: int
    ) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(available_at) FROM quantlab_fixture_context_observations "
                "WHERE fixture_id = %s",
                (fixture_id,),
            )
            row = cursor.fetchone()
        last = None if row is None else row[0]
        return last is None or last <= now - timedelta(seconds=refresh_seconds)

    def feature_snapshot_due(
        self, fixture_id: str, *, now: datetime, refresh_seconds: int
    ) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(decision_at) FROM quantlab_card_feature_snapshots WHERE fixture_id = %s",
                (fixture_id,),
            )
            row = cursor.fetchone()
        last = None if row is None else row[0]
        return last is None or last <= now - timedelta(seconds=refresh_seconds)

    def statistics_exists(self, fixture_id: str) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM quantlab_match_statistics_observations "
                "WHERE fixture_id = %s)",
                (fixture_id,),
            )
            return bool(cursor.fetchone()[0])

    def save_market_observations(self, observations: Iterable[Any]) -> int:
        rows = tuple(observations)
        if not rows:
            return 0
        with self.connect() as connection, connection.cursor() as cursor:
            count = 0
            for item in rows:
                cursor.execute(
                    "INSERT INTO quantlab_market_observations ("
                    "market_observation_id, fixture_id, provider_fixture_id, bookmaker_id, "
                    "bookmaker_name, provider_bet_id, provider_bet_name, raw_selection, "
                    "parsed_line, odds, provider_updated_at, captured_at, lab_owner, "
                    "classifier_version, raw_payload"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    (
                        item.market_observation_id,
                        item.fixture_id,
                        item.provider_fixture_id,
                        item.bookmaker_id,
                        item.bookmaker_name,
                        item.provider_bet_id,
                        item.provider_bet_name,
                        item.raw_selection,
                        item.parsed_line,
                        item.odds,
                        item.provider_updated_at,
                        item.captured_at,
                        item.lab_owner,
                        item.classifier_version,
                        _json(item.raw_payload),
                    ),
                )
                count += max(0, cursor.rowcount)
            return count

    def save_fixture_context(self, item: Any) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_fixture_context_observations ("
                "context_observation_id, fixture_id, provider_fixture_id, referee, "
                "provider_status, kickoff_at, provider_updated_at, available_at, raw_payload"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT DO NOTHING",
                (
                    item.context_observation_id,
                    item.fixture_id,
                    item.provider_fixture_id,
                    item.referee,
                    item.provider_status,
                    item.kickoff_at,
                    item.provider_updated_at,
                    item.available_at,
                    _json(item.raw_payload),
                ),
            )

    def save_match_statistics(self, item: Any) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_match_statistics_observations ("
                "statistics_observation_id, fixture_id, provider_fixture_id, home_fouls, "
                "away_fouls, home_yellow_cards, away_yellow_cards, home_red_cards, "
                "away_red_cards, home_second_yellow_cards, away_second_yellow_cards, "
                "available_at, raw_payload"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                "ON CONFLICT DO NOTHING",
                (
                    item.statistics_observation_id,
                    item.fixture_id,
                    item.provider_fixture_id,
                    item.home_fouls,
                    item.away_fouls,
                    item.home_yellow_cards,
                    item.away_yellow_cards,
                    item.home_red_cards,
                    item.away_red_cards,
                    item.home_second_yellow_cards,
                    item.away_second_yellow_cards,
                    item.available_at,
                    _json(item.raw_payload),
                ),
            )

    def save_standings_snapshot(
        self,
        *,
        league_id: int,
        season: int,
        available_at: datetime,
        raw_payload: dict[str, Any],
    ) -> str:
        snapshot_id = _identifier(
            "quantlab-standings-v1:",
            {
                "league_id": league_id,
                "season": season,
                "available_at": available_at.isoformat(),
                "raw_payload": raw_payload,
            },
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_standings_snapshots ("
                "standings_snapshot_id, league_id, season, available_at, raw_payload"
                ") VALUES (%s, %s, %s, %s, %s::jsonb) ON CONFLICT DO NOTHING",
                (snapshot_id, league_id, season, available_at, _json(raw_payload)),
            )
        return snapshot_id

    def latest_standings_before(
        self, league_id: int, season: int, *, decision_at: datetime
    ) -> dict[str, Any] | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT available_at, raw_payload FROM quantlab_standings_snapshots "
                "WHERE league_id = %s AND season = %s AND available_at <= %s "
                "ORDER BY available_at DESC, standings_snapshot_id DESC LIMIT 1",
                (league_id, season, decision_at),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        return {"available_at": row[0], "raw_payload": payload}

    def latest_context_before(
        self, fixture_id: str, *, decision_at: datetime
    ) -> dict[str, Any] | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT referee, kickoff_at, available_at, provider_status, raw_payload "
                "FROM quantlab_fixture_context_observations "
                "WHERE fixture_id = %s AND available_at <= %s "
                "ORDER BY available_at DESC, context_observation_id DESC LIMIT 1",
                (fixture_id, decision_at),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = json.loads(row[4]) if isinstance(row[4], str) else row[4]
        return {
            "referee": row[0],
            "kickoff_at": row[1],
            "available_at": row[2],
            "provider_status": row[3],
            "raw_payload": payload,
        }

    def referee_history(
        self, referee: str, *, decision_at: datetime, limit: int = 80
    ) -> tuple[dict[str, Any], ...]:
        if not referee.strip():
            return ()
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "WITH context AS ("
                " SELECT DISTINCT ON (fixture_id) fixture_id, referee, kickoff_at, available_at "
                " FROM quantlab_fixture_context_observations "
                " WHERE lower(referee) = lower(%s) AND available_at <= %s "
                " ORDER BY fixture_id, available_at DESC, context_observation_id DESC"
                "), stats AS ("
                " SELECT DISTINCT ON (fixture_id) fixture_id, available_at, "
                " home_fouls, away_fouls, home_yellow_cards, away_yellow_cards, "
                " home_red_cards, away_red_cards, home_second_yellow_cards, away_second_yellow_cards "
                " FROM quantlab_match_statistics_observations WHERE available_at <= %s "
                " ORDER BY fixture_id, available_at DESC, statistics_observation_id DESC"
                ") "
                "SELECT context.referee, context.kickoff_at, "
                "GREATEST(context.available_at, stats.available_at) AS available_at, "
                "CASE WHEN stats.home_yellow_cards IS NULL OR stats.away_yellow_cards IS NULL "
                " THEN NULL ELSE stats.home_yellow_cards + stats.away_yellow_cards END AS yellow_cards, "
                "CASE WHEN stats.home_red_cards IS NULL OR stats.away_red_cards IS NULL "
                " THEN NULL ELSE stats.home_red_cards + stats.away_red_cards END AS red_cards, "
                "CASE WHEN stats.home_second_yellow_cards IS NULL OR stats.away_second_yellow_cards IS NULL "
                " THEN NULL ELSE stats.home_second_yellow_cards + stats.away_second_yellow_cards END AS second_yellow_cards, "
                "CASE WHEN stats.home_fouls IS NULL OR stats.away_fouls IS NULL "
                " THEN NULL ELSE stats.home_fouls + stats.away_fouls END AS fouls "
                "FROM context JOIN stats USING (fixture_id) "
                "WHERE context.kickoff_at < %s "
                "ORDER BY context.kickoff_at DESC LIMIT %s",
                (referee, decision_at, decision_at, decision_at, limit),
            )
            return _row_dicts(cursor)

    def save_card_feature_snapshot(self, item: Any) -> str:
        snapshot_id = _identifier(
            "quantlab-card-features-v1:",
            {
                "fixture_id": item.fixture_id,
                "decision_at": item.decision_at.isoformat(),
                "feature_version": item.feature_version,
            },
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_card_feature_snapshots ("
                "feature_snapshot_id, fixture_id, decision_at, available_at, referee, "
                "referee_card_rate, referee_sample_size, referee_foul_rate, "
                "referee_foul_sample_size, derby_rivalry_indicator, home_table_pressure, "
                "away_table_pressure, table_pressure, match_importance, feature_version, "
                "feature_payload"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                "ON CONFLICT DO NOTHING",
                (
                    snapshot_id,
                    item.fixture_id,
                    item.decision_at,
                    item.available_at,
                    item.referee,
                    item.referee_card_rate,
                    item.referee_sample_size,
                    item.referee_foul_rate,
                    item.referee_foul_sample_size,
                    item.derby_rivalry_indicator,
                    item.home_table_pressure,
                    item.away_table_pressure,
                    item.table_pressure,
                    item.match_importance,
                    item.feature_version,
                    _json(item.feature_payload),
                ),
            )
        return snapshot_id

    def list_card_features(self, *, limit: int = 500) -> tuple[dict[str, Any], ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT ON (q.fixture_id) q.feature_snapshot_id, q.fixture_id, "
                "q.decision_at, q.available_at, q.referee, q.referee_card_rate, "
                "q.referee_sample_size, q.referee_foul_rate, q.referee_foul_sample_size, "
                "q.derby_rivalry_indicator, q.home_table_pressure, q.away_table_pressure, "
                "q.table_pressure, q.match_importance, q.feature_version, q.feature_payload, "
                "latest.home_team, latest.away_team, latest.competition_name, "
                "latest.country, latest.kickoff_at "
                "FROM quantlab_card_feature_snapshots q "
                "JOIN LATERAL (SELECT home_team, away_team, competition_name, country, kickoff_at "
                "FROM fixture_observations o WHERE o.fixture_id = q.fixture_id "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1) latest ON TRUE "
                "ORDER BY q.fixture_id, q.decision_at DESC, q.feature_snapshot_id DESC LIMIT %s",
                (limit,),
            )
            return _row_dicts(cursor)

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
