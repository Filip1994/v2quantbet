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
            "quantlab_market_captures",
            "quantlab_goal_decisions",
            "quantlab_context_market_decisions",
            "quantlab_fixture_context_observations",
            "quantlab_match_statistics_observations",
            "quantlab_statistics_captures",
            "quantlab_standings_snapshots",
            "quantlab_card_feature_snapshots",
            "quantlab_corner_model_versions",
            "quantlab_corner_feature_snapshots",
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

    def goal_market_pairs(
        self,
        fixture_id: str,
        *,
        decision_at: datetime,
    ) -> tuple[dict[str, Any], ...]:
        """Return latest complete canonical GoalLab pairs per bookmaker/market."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT market_observation_id, bookmaker_id, bookmaker_name, provider_bet_id, "
                "provider_bet_name, raw_selection, parsed_line, odds, provider_updated_at, "
                "captured_at FROM quantlab_market_observations "
                "WHERE fixture_id = %s AND lab_owner = 'GOAL' "
                "AND provider_bet_id IN (5, 8) AND captured_at <= %s "
                "ORDER BY captured_at DESC, bookmaker_id, provider_bet_id, market_observation_id",
                (fixture_id, decision_at),
            )
            rows = _row_dicts(cursor)

        grouped: dict[tuple[int, int, datetime], dict[str, dict[str, Any]]] = {}
        metadata: dict[tuple[int, int, datetime], dict[str, Any]] = {}
        for row in rows:
            bet_id = int(row["provider_bet_id"])
            raw = str(row["raw_selection"] or "").strip().casefold()
            line = row.get("parsed_line")
            if bet_id == 5:
                if line is None or abs(float(line) - 2.5) > 1e-9:
                    continue
                if raw == "over 2.5":
                    selection, market_key = "OVER", "OU_25"
                elif raw == "under 2.5":
                    selection, market_key = "UNDER", "OU_25"
                else:
                    continue
            else:
                if raw == "yes":
                    selection, market_key = "YES", "BTTS"
                elif raw == "no":
                    selection, market_key = "NO", "BTTS"
                else:
                    continue
            key = (int(row["bookmaker_id"]), bet_id, row["captured_at"])
            grouped.setdefault(key, {})[selection] = row
            metadata[key] = {
                "bookmaker_id": int(row["bookmaker_id"]),
                "bookmaker_name": str(row["bookmaker_name"]),
                "provider_bet_id": bet_id,
                "provider_bet_name": str(row["provider_bet_name"]),
                "market_key": market_key,
                "line": 2.5 if market_key == "OU_25" else None,
                "captured_at": row["captured_at"],
            }

        latest: dict[tuple[int, str], dict[str, Any]] = {}
        expected = {"OU_25": {"OVER", "UNDER"}, "BTTS": {"YES", "NO"}}
        for key, selections in grouped.items():
            meta = metadata[key]
            if set(selections) != expected[meta["market_key"]]:
                continue
            pair = {**meta, "selections": dict(selections)}
            logical = (meta["bookmaker_id"], meta["market_key"])
            current = latest.get(logical)
            if current is None or pair["captured_at"] > current["captured_at"]:
                latest[logical] = pair
        return tuple(
            sorted(
                latest.values(),
                key=lambda item: (
                    str(item["market_key"]),
                    int(item["bookmaker_id"]),
                ),
            )
        )

    def market_labs_for_fixture(self, fixture_id: str) -> frozenset[str]:
        """Return lab owners for persisted markets on one fixture."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT lab_owner FROM quantlab_market_observations "
                "WHERE fixture_id = %s",
                (fixture_id,),
            )
            return frozenset(str(row[0]) for row in cursor.fetchall())

    def total_market_pairs(
        self,
        fixture_id: str,
        *,
        lab_owner: str,
        decision_at: datetime,
    ) -> tuple[dict[str, Any], ...]:
        """Return latest complete two-sided over/under totals for one lab."""
        if lab_owner not in {"CORNER", "CARD"}:
            raise ValueError("lab_owner must be CORNER or CARD")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT market_observation_id, bookmaker_id, bookmaker_name, provider_bet_id, "
                "provider_bet_name, raw_selection, parsed_line, odds, provider_updated_at, "
                "captured_at FROM quantlab_market_observations "
                "WHERE fixture_id = %s AND lab_owner = %s AND parsed_line IS NOT NULL "
                "AND captured_at <= %s "
                "ORDER BY captured_at DESC, bookmaker_id, provider_bet_id, "
                "parsed_line, market_observation_id",
                (fixture_id, lab_owner, decision_at),
            )
            rows = _row_dicts(cursor)

        grouped: dict[
            tuple[int, int, str, datetime, float],
            dict[str, dict[str, Any]],
        ] = {}
        metadata: dict[tuple[int, int, str, datetime, float], dict[str, Any]] = {}
        for row in rows:
            raw = str(row["raw_selection"] or "").strip().casefold()
            if raw.startswith("over "):
                selection = "OVER"
            elif raw.startswith("under "):
                selection = "UNDER"
            else:
                continue
            line = float(row["parsed_line"])
            bet_name = str(row["provider_bet_name"])
            key = (
                int(row["bookmaker_id"]),
                int(row["provider_bet_id"]),
                bet_name.casefold(),
                row["captured_at"],
                line,
            )
            grouped.setdefault(key, {})[selection] = row
            metadata[key] = {
                "bookmaker_id": int(row["bookmaker_id"]),
                "bookmaker_name": str(row["bookmaker_name"]),
                "provider_bet_id": int(row["provider_bet_id"]),
                "provider_bet_name": bet_name,
                "line": line,
                "captured_at": row["captured_at"],
            }

        latest: dict[tuple[int, int, str, float], dict[str, Any]] = {}
        for key, selections in grouped.items():
            if set(selections) != {"OVER", "UNDER"}:
                continue
            meta = metadata[key]
            logical = (
                int(meta["bookmaker_id"]),
                int(meta["provider_bet_id"]),
                str(meta["provider_bet_name"]).casefold(),
                float(meta["line"]),
            )
            pair = {**meta, "selections": dict(selections)}
            current = latest.get(logical)
            if current is None or pair["captured_at"] > current["captured_at"]:
                latest[logical] = pair
        return tuple(
            sorted(
                latest.values(),
                key=lambda item: (
                    int(item["provider_bet_id"]),
                    float(item["line"]),
                    int(item["bookmaker_id"]),
                ),
            )
        )

    def save_goal_decision(self, item: Any) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_goal_decisions ("
                "decision_id, fixture_id, decision_at, policy_version, model_name, model_version, "
                "bookmaker_id, bookmaker_name, provider_bet_id, provider_bet_name, market_key, "
                "selection, line, selected_observation_id, companion_observation_id, "
                "quote_observed_at, odds, companion_odds, market_probability, model_probability, "
                "edge, expected_value, decision, reason, evidence_fingerprint, details"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT DO NOTHING",
                (
                    item.decision_id,
                    item.fixture_id,
                    item.decision_at,
                    item.policy_version,
                    item.model_name,
                    item.model_version,
                    item.bookmaker_id,
                    item.bookmaker_name,
                    item.provider_bet_id,
                    item.provider_bet_name,
                    item.market_key,
                    item.selection,
                    item.line,
                    item.selected_observation_id,
                    item.companion_observation_id,
                    item.quote_observed_at,
                    item.odds,
                    item.companion_odds,
                    item.market_probability,
                    item.model_probability,
                    item.edge,
                    item.expected_value,
                    item.decision,
                    item.reason,
                    item.evidence_fingerprint,
                    _json(item.details),
                ),
            )
            return cursor.rowcount > 0

    def save_goal_shadow_bet(self, item: Any, *, stake_minor: int) -> bool:
        if item.decision != "PICK":
            raise ValueError("only PICK decisions may create shadow bets")
        shadow_bet_id = _identifier(
            "quantlab-shadow-v1:",
            {
                "fixture_id": item.fixture_id,
                "lab": "GOAL",
                "market_key": item.market_key,
                "selection": item.selection,
                "line": item.line,
            },
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_shadow_bets ("
                "shadow_bet_id, fixture_id, lab, bookmaker_id, bookmaker_name, provider_bet_id, "
                "provider_bet_name, market_key, selection, line, model_name, model_version, "
                "model_probability, market_probability, edge, expected_value, odds, "
                "quote_observed_at, decision_at, stake_minor"
                ") VALUES (%s, %s, 'GOAL', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    shadow_bet_id,
                    item.fixture_id,
                    item.bookmaker_id,
                    item.bookmaker_name,
                    item.provider_bet_id,
                    item.provider_bet_name,
                    item.market_key,
                    item.selection,
                    item.line,
                    item.model_name,
                    item.model_version,
                    item.model_probability,
                    item.market_probability,
                    item.edge,
                    item.expected_value,
                    item.odds,
                    item.quote_observed_at,
                    item.decision_at,
                    stake_minor,
                ),
            )
            return cursor.rowcount > 0

    def save_context_market_decision(self, item: Any) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_context_market_decisions ("
                "decision_id, fixture_id, lab, decision_at, policy_version, model_name, "
                "model_version, bookmaker_id, bookmaker_name, reference_bookmaker_id, "
                "reference_bookmaker_name, provider_bet_id, provider_bet_name, market_key, "
                "selection, line, selected_observation_id, companion_observation_id, "
                "reference_observation_id, reference_companion_observation_id, "
                "quote_observed_at, reference_quote_observed_at, odds, companion_odds, "
                "reference_odds, reference_companion_odds, market_probability, "
                "model_probability, edge, expected_value, decision, reason, "
                "evidence_fingerprint, details"
                ") VALUES ("
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s::jsonb) ON CONFLICT DO NOTHING",
                (
                    item.decision_id,
                    item.fixture_id,
                    item.lab,
                    item.decision_at,
                    item.policy_version,
                    item.model_name,
                    item.model_version,
                    item.bookmaker_id,
                    item.bookmaker_name,
                    item.reference_bookmaker_id,
                    item.reference_bookmaker_name,
                    item.provider_bet_id,
                    item.provider_bet_name,
                    item.market_key,
                    item.selection,
                    item.line,
                    item.selected_observation_id,
                    item.companion_observation_id,
                    item.reference_observation_id,
                    item.reference_companion_observation_id,
                    item.quote_observed_at,
                    item.reference_quote_observed_at,
                    item.odds,
                    item.companion_odds,
                    item.reference_odds,
                    item.reference_companion_odds,
                    item.market_probability,
                    item.model_probability,
                    item.edge,
                    item.expected_value,
                    item.decision,
                    item.reason,
                    item.evidence_fingerprint,
                    _json(item.details),
                ),
            )
            return cursor.rowcount > 0

    def save_context_shadow_bet(self, item: Any, *, stake_minor: int) -> bool:
        if item.lab not in {"CORNER", "CARD"}:
            raise ValueError("context shadow bet lab must be CORNER or CARD")
        if item.decision != "PICK":
            raise ValueError("only PICK decisions may create shadow bets")
        shadow_bet_id = _identifier(
            "quantlab-shadow-v1:",
            {
                "fixture_id": item.fixture_id,
                "lab": item.lab,
                "market_key": item.market_key,
                "selection": item.selection,
                "line": item.line,
            },
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_shadow_bets ("
                "shadow_bet_id, fixture_id, lab, bookmaker_id, bookmaker_name, provider_bet_id, "
                "provider_bet_name, market_key, selection, line, model_name, model_version, "
                "model_probability, market_probability, edge, expected_value, odds, "
                "quote_observed_at, decision_at, stake_minor"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    shadow_bet_id,
                    item.fixture_id,
                    item.lab,
                    item.bookmaker_id,
                    item.bookmaker_name,
                    item.provider_bet_id,
                    item.provider_bet_name,
                    item.market_key,
                    item.selection,
                    item.line,
                    item.model_name,
                    item.model_version,
                    item.model_probability,
                    item.market_probability,
                    item.edge,
                    item.expected_value,
                    item.odds,
                    item.quote_observed_at,
                    item.decision_at,
                    stake_minor,
                ),
            )
            return cursor.rowcount > 0

    def list_goal_fixture_status(
        self,
        *,
        now: datetime,
        lookahead_hours: int = 36,
        limit: int = 250,
    ) -> tuple[dict[str, Any], ...]:
        end_at = now + timedelta(hours=lookahead_hours)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT f.fixture_id, latest.league_id, latest.season, latest.home_team_id, "
                "latest.away_team_id, latest.home_team, latest.away_team, latest.competition_name, "
                "latest.country, latest.competition_type, latest.kickoff_at, latest.provider_status, "
                "capture.captured_at AS market_captured_at, decision.decision_at, "
                "decision.decision, decision.reason, decision.model_version, decision.market_key, "
                "decision.selection, decision.bookmaker_name, decision.odds, decision.edge, "
                "decision.expected_value "
                "FROM quantlab_fixtures f "
                "JOIN LATERAL ("
                " SELECT league_id, season, home_team_id, away_team_id, home_team, away_team, "
                "        competition_name, country, competition_type, kickoff_at, provider_status "
                " FROM quantlab_fixture_observations o WHERE o.fixture_id = f.fixture_id "
                " ORDER BY captured_at DESC, fixture_observation_id DESC LIMIT 1"
                ") latest ON TRUE "
                "LEFT JOIN LATERAL ("
                " SELECT captured_at FROM quantlab_market_captures c WHERE c.fixture_id = f.fixture_id "
                " ORDER BY captured_at DESC, market_capture_id DESC LIMIT 1"
                ") capture ON TRUE "
                "LEFT JOIN LATERAL ("
                " SELECT decision_at, decision, reason, model_version, market_key, selection, "
                "        bookmaker_name, odds, edge, expected_value "
                " FROM quantlab_goal_decisions d WHERE d.fixture_id = f.fixture_id "
                " ORDER BY decision_at DESC, (decision = 'PICK') DESC, decision_id DESC LIMIT 1"
                ") decision ON TRUE "
                "WHERE latest.kickoff_at >= %s AND latest.kickoff_at < %s "
                "ORDER BY latest.kickoff_at, f.fixture_id LIMIT %s",
                (now, end_at, limit),
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
                "AND NOT EXISTS (SELECT 1 FROM quantlab_statistics_captures sc "
                "                WHERE sc.fixture_id = f.fixture_id "
                "                  AND sc.reason IS DISTINCT FROM 'legacy-statistics-observation') "
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
                "AND NOT EXISTS (SELECT 1 FROM quantlab_statistics_captures sc "
                "                WHERE sc.fixture_id = f.fixture_id "
                "                  AND sc.reason IS DISTINCT FROM 'legacy-statistics-observation') "
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
                "SELECT MAX(captured_at) FROM ("
                " SELECT captured_at FROM quantlab_market_captures WHERE fixture_id = %s"
                " UNION ALL "
                " SELECT captured_at FROM quantlab_market_observations WHERE fixture_id = %s"
                ") captures",
                (fixture_id, fixture_id),
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

    def statistics_capture_exists(self, fixture_id: str) -> bool:
        """Return whether CornerLab V2 enrichment has already been attempted.

        Migration 032 seeded legacy captures for pre-V2 card/foul-only statistics.
        Those rows deliberately do not block the one-time pressure-statistics refresh.
        """
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM quantlab_statistics_captures "
                "WHERE fixture_id = %s "
                "AND reason IS DISTINCT FROM 'legacy-statistics-observation')",
                (fixture_id,),
            )
            return bool(cursor.fetchone()[0])

    def save_statistics_capture(
        self,
        *,
        fixture_id: str,
        provider_fixture_id: int,
        captured_at: datetime,
        status: str,
        response_team_count: int,
        reason: str | None,
        raw_payload: dict[str, Any],
    ) -> str:
        if status not in {"AVAILABLE", "UNAVAILABLE"}:
            raise ValueError("statistics capture status must be AVAILABLE or UNAVAILABLE")
        capture_id = _identifier(
            "quantlab-stats-capture-v1:",
            {
                "fixture_id": fixture_id,
                "provider_fixture_id": provider_fixture_id,
                "captured_at": captured_at.isoformat(),
                "status": status,
                "response_team_count": response_team_count,
                "reason": reason,
            },
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_statistics_captures ("
                "statistics_capture_id, fixture_id, provider_fixture_id, captured_at, "
                "status, response_team_count, reason, raw_payload"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                "ON CONFLICT DO NOTHING",
                (
                    capture_id,
                    fixture_id,
                    provider_fixture_id,
                    captured_at,
                    status,
                    response_team_count,
                    reason,
                    _json(raw_payload),
                ),
            )
        return capture_id

    def save_market_capture(
        self,
        *,
        fixture_id: str,
        provider_fixture_id: int,
        captured_at: datetime,
        raw_observation_count: int,
        stored_observation_count: int,
        allowed_labs: Iterable[str],
    ) -> str:
        labs = tuple(sorted({str(lab) for lab in allowed_labs}))
        capture_id = _identifier(
            "quantlab-market-capture-v1:",
            {
                "fixture_id": fixture_id,
                "provider_fixture_id": provider_fixture_id,
                "captured_at": captured_at.isoformat(),
                "raw_observation_count": raw_observation_count,
                "stored_observation_count": stored_observation_count,
                "allowed_labs": labs,
            },
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_market_captures ("
                "market_capture_id, fixture_id, provider_fixture_id, captured_at, "
                "raw_observation_count, stored_observation_count, allowed_labs"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT DO NOTHING",
                (
                    capture_id,
                    fixture_id,
                    provider_fixture_id,
                    captured_at,
                    raw_observation_count,
                    stored_observation_count,
                    _json(labs),
                ),
            )
        return capture_id

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
                "home_corner_kicks, away_corner_kicks, home_ball_possession, "
                "away_ball_possession, home_shots_on_goal, away_shots_on_goal, "
                "home_shots_off_goal, away_shots_off_goal, home_total_shots, "
                "away_total_shots, home_blocked_shots, away_blocked_shots, "
                "home_shots_insidebox, away_shots_insidebox, home_shots_outsidebox, "
                "away_shots_outsidebox, home_offsides, away_offsides, "
                "home_goalkeeper_saves, away_goalkeeper_saves, home_total_passes, "
                "away_total_passes, home_passes_accurate, away_passes_accurate, "
                "home_pass_accuracy, away_pass_accuracy, available_at, raw_payload"
                ") VALUES ("
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb"
                ") ON CONFLICT DO NOTHING",
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
                    item.home_corner_kicks,
                    item.away_corner_kicks,
                    item.home_ball_possession,
                    item.away_ball_possession,
                    item.home_shots_on_goal,
                    item.away_shots_on_goal,
                    item.home_shots_off_goal,
                    item.away_shots_off_goal,
                    item.home_total_shots,
                    item.away_total_shots,
                    item.home_blocked_shots,
                    item.away_blocked_shots,
                    item.home_shots_insidebox,
                    item.away_shots_insidebox,
                    item.home_shots_outsidebox,
                    item.away_shots_outsidebox,
                    item.home_offsides,
                    item.away_offsides,
                    item.home_goalkeeper_saves,
                    item.away_goalkeeper_saves,
                    item.home_total_passes,
                    item.away_total_passes,
                    item.home_passes_accurate,
                    item.away_passes_accurate,
                    item.home_pass_accuracy,
                    item.away_pass_accuracy,
                    item.available_at,
                    _json(item.raw_payload),
                ),
            )

    def corner_model_history(
        self,
        *,
        before: datetime,
        limit: int = 6000,
    ) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT s.fixture_id, s.available_at, "
                "COALESCE(q.latest_kickoff, p.latest_kickoff) AS kickoff_at, "
                "COALESCE(q.home_team_id, f.provider_home_team_id::BIGINT) AS home_team_id, "
                "COALESCE(q.away_team_id, f.provider_away_team_id::BIGINT) AS away_team_id, "
                "s.home_corner_kicks, s.away_corner_kicks, "
                "s.home_ball_possession, s.away_ball_possession, "
                "s.home_shots_on_goal, s.away_shots_on_goal, "
                "s.home_total_shots, s.away_total_shots, "
                "s.home_blocked_shots, s.away_blocked_shots, "
                "s.home_shots_insidebox, s.away_shots_insidebox, "
                "s.home_offsides, s.away_offsides, "
                "s.home_total_passes, s.away_total_passes, "
                "s.home_passes_accurate, s.away_passes_accurate, "
                "s.home_pass_accuracy, s.away_pass_accuracy "
                "FROM quantlab_match_statistics_observations s "
                "LEFT JOIN fixtures f ON f.fixture_id = s.fixture_id "
                "LEFT JOIN LATERAL ("
                " SELECT o.kickoff_at AS latest_kickoff, o.home_team_id, o.away_team_id "
                " FROM quantlab_fixture_observations o "
                " WHERE o.fixture_id = s.fixture_id "
                " ORDER BY o.captured_at DESC, o.fixture_observation_id DESC LIMIT 1"
                ") q ON TRUE "
                "LEFT JOIN LATERAL ("
                " SELECT o.kickoff_at AS latest_kickoff "
                " FROM fixture_observations o "
                " WHERE o.fixture_id = s.fixture_id "
                " ORDER BY o.observed_at DESC, o.fixture_observation_id DESC LIMIT 1"
                ") p ON TRUE "
                "WHERE COALESCE(q.latest_kickoff, p.latest_kickoff) < %s "
                "AND s.available_at <= %s "
                "AND s.home_corner_kicks IS NOT NULL "
                "AND s.away_corner_kicks IS NOT NULL "
                "AND COALESCE(q.home_team_id, f.provider_home_team_id::BIGINT) IS NOT NULL "
                "AND COALESCE(q.away_team_id, f.provider_away_team_id::BIGINT) IS NOT NULL "
                "ORDER BY COALESCE(q.latest_kickoff, p.latest_kickoff) DESC, s.available_at DESC "
                "LIMIT %s",
                (before, before, limit),
            )
            rows = _row_dicts(cursor)
        return tuple(reversed(rows))

    def save_corner_model_version(self, item: Any) -> bool:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_corner_model_versions ("
                "model_version, trained_at, training_cutoff, feature_version, "
                "training_sample_size, history_match_count, ridge_penalty, coefficients, "
                "feature_means, feature_scales, training_payload"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, "
                "%s::jsonb) ON CONFLICT DO NOTHING",
                (
                    item.model_version,
                    item.trained_at,
                    item.training_cutoff,
                    item.feature_version,
                    item.training_sample_size,
                    item.history_match_count,
                    item.ridge_penalty,
                    _json(item.coefficients),
                    _json(item.feature_means),
                    _json(item.feature_scales),
                    _json(item.training_payload),
                ),
            )
            return cursor.rowcount > 0

    def save_corner_feature_snapshot(self, item: Any) -> str:
        snapshot_id = _identifier(
            "quantlab-corner-features-v1:",
            {
                "fixture_id": item.fixture_id,
                "decision_at": item.decision_at.isoformat(),
                "model_version": item.model_version,
            },
        )
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO quantlab_corner_feature_snapshots ("
                "feature_snapshot_id, fixture_id, decision_at, model_version, "
                "expected_total_corners, home_history_size, away_history_size, feature_payload"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                "ON CONFLICT DO NOTHING",
                (
                    snapshot_id,
                    item.fixture_id,
                    item.decision_at,
                    item.model_version,
                    item.expected_total_corners,
                    item.home_history_size,
                    item.away_history_size,
                    _json(item.feature_payload),
                ),
            )
        return snapshot_id

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

    def latest_card_feature_snapshot(
        self, fixture_id: str, *, decision_at: datetime
    ) -> dict[str, Any] | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT feature_snapshot_id, fixture_id, decision_at, available_at, referee, "
                "referee_card_rate, referee_sample_size, referee_foul_rate, "
                "referee_foul_sample_size, derby_rivalry_indicator, home_table_pressure, "
                "away_table_pressure, table_pressure, match_importance, feature_version, "
                "feature_payload FROM quantlab_card_feature_snapshots "
                "WHERE fixture_id = %s AND decision_at <= %s AND available_at <= %s "
                "ORDER BY decision_at DESC, feature_snapshot_id DESC LIMIT 1",
                (fixture_id, decision_at, decision_at),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            columns = tuple(item.name for item in cursor.description)
            result = dict(zip(columns, row, strict=True))
        payload = result.get("feature_payload")
        if isinstance(payload, str):
            result["feature_payload"] = json.loads(payload)
        return result

    def list_card_features(self, *, limit: int = 500) -> tuple[dict[str, Any], ...]:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT ON (q.fixture_id) q.feature_snapshot_id, q.fixture_id, "
                "q.decision_at, q.available_at, q.referee, q.referee_card_rate, "
                "q.referee_sample_size, q.referee_foul_rate, q.referee_foul_sample_size, "
                "q.derby_rivalry_indicator, q.home_table_pressure, q.away_table_pressure, "
                "q.table_pressure, q.match_importance, q.feature_version, q.feature_payload, "
                "COALESCE(qlatest.home_team, platest.home_team) AS home_team, "
                "COALESCE(qlatest.away_team, platest.away_team) AS away_team, "
                "COALESCE(qlatest.competition_name, platest.competition_name) AS competition_name, "
                "COALESCE(qlatest.country, platest.country) AS country, "
                "COALESCE(qlatest.kickoff_at, platest.kickoff_at) AS kickoff_at "
                "FROM quantlab_card_feature_snapshots q "
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
