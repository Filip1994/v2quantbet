"""PostgreSQL repository for durable fixtures and append-only observations."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from h2h.domain.fixture import Fixture
from h2h.domain.fixture_record import FixtureIdentityRecord, FixtureObservation, PersistedFixture
from h2h.persistence.fixtures import FixturePersistenceConflictError


ConnectionFactory = Callable[[], Any]
LOGGER = logging.getLogger("quantbet.fixtures")


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _observation_id(fixture_id: str, observed_at: datetime, source: str) -> str:
    payload = json.dumps(
        {"fixture_id": fixture_id, "observed_at": observed_at.isoformat(), "source": source},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "fixture-observation-v1:" + sha256(payload).hexdigest()


class PostgreSQLFixtureRepository:
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

    def record_discovery(self, fixture: Fixture, *, observed_at: object) -> PersistedFixture:
        if not isinstance(fixture, Fixture):
            raise TypeError("fixture must be a Fixture")
        observed = _utc(observed_at, "observed_at")
        kickoff = _utc(fixture.kickoff_at, "fixture.kickoff_at")
        required = {
            "provider_fixture_id": fixture.provider_fixture_id,
            "season": fixture.season,
            "provider_home_team_id": fixture.provider_home_team_id,
            "provider_away_team_id": fixture.provider_away_team_id,
        }
        if any(value is None for value in required.values()):
            missing = next(name for name, value in required.items() if value is None)
            raise ValueError(f"fixture.{missing} is required for durable persistence")
        if fixture.provider_home_team_id == fixture.provider_away_team_id:
            raise ValueError("provider home and away team IDs must be different")
        observation_id = _observation_id(fixture.fixture_id, observed, fixture.provider)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id, provider, provider_fixture_id, league_id, season, "
                "provider_home_team_id, provider_away_team_id, created_at FROM fixtures "
                "WHERE fixture_id = %s OR (provider = %s AND provider_fixture_id = %s)",
                (fixture.fixture_id, fixture.provider, fixture.provider_fixture_id),
            )
            rows = cursor.fetchall()
            if len(rows) > 1:
                raise FixturePersistenceConflictError(
                    "canonical and provider identities resolve differently"
                )
            if not rows:
                cursor.execute(
                    "INSERT INTO fixtures (fixture_id, provider, provider_fixture_id, league_id, "
                    "season, provider_home_team_id, provider_away_team_id, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (
                        fixture.fixture_id,
                        fixture.provider,
                        fixture.provider_fixture_id,
                        fixture.competition_id,
                        fixture.season,
                        fixture.provider_home_team_id,
                        fixture.provider_away_team_id,
                        observed,
                    ),
                )
                cursor.execute(
                    "SELECT fixture_id, provider, provider_fixture_id, league_id, season, "
                    "provider_home_team_id, provider_away_team_id, created_at FROM fixtures "
                    "WHERE fixture_id = %s OR (provider = %s AND provider_fixture_id = %s)",
                    (fixture.fixture_id, fixture.provider, fixture.provider_fixture_id),
                )
                rows = cursor.fetchall()
            if len(rows) != 1:
                raise FixturePersistenceConflictError("fixture identity could not be resolved")
            identity = self._row_to_identity(rows[0])
            expected_anchor = (
                fixture.fixture_id,
                fixture.provider,
                fixture.provider_fixture_id,
                fixture.competition_id,
                fixture.season,
                fixture.provider_home_team_id,
                fixture.provider_away_team_id,
            )
            actual_anchor = (
                identity.fixture_id,
                identity.provider,
                identity.provider_fixture_id,
                identity.league_id,
                identity.season,
                identity.provider_home_team_id,
                identity.provider_away_team_id,
            )
            if actual_anchor != expected_anchor:
                field_names = (
                    "fixture_id",
                    "provider",
                    "provider_fixture_id",
                    "league_id",
                    "season",
                    "provider_home_team_id",
                    "provider_away_team_id",
                )
                conflicting_fields = tuple(
                    name
                    for name, stored, incoming in zip(
                        field_names, actual_anchor, expected_anchor, strict=True
                    )
                    if stored != incoming
                )
                LOGGER.error(
                    "immutable fixture identity conflict detected",
                    extra={
                        "fixture_id": fixture.fixture_id,
                        "provider": fixture.provider,
                        "provider_fixture_id": fixture.provider_fixture_id,
                        "league_id": fixture.competition_id,
                        "season": fixture.season,
                        "provider_home_team_id": fixture.provider_home_team_id,
                        "provider_away_team_id": fixture.provider_away_team_id,
                        "stored_fixture_identity": actual_anchor,
                        "incoming_fixture_identity": expected_anchor,
                        "conflicting_identity_fields": conflicting_fields,
                    },
                )
                raise FixturePersistenceConflictError("immutable fixture identity conflicts")

            cursor.execute(
                "INSERT INTO fixture_observations (fixture_observation_id, fixture_id, home_team, "
                "away_team, competition_name, country, competition_type, kickoff_at, "
                "provider_status, source, observed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    observation_id,
                    fixture.fixture_id,
                    fixture.home_team,
                    fixture.away_team,
                    fixture.competition_name,
                    fixture.country,
                    fixture.competition_type,
                    kickoff,
                    fixture.status,
                    fixture.provider,
                    observed,
                ),
            )
            cursor.execute(
                "SELECT fixture_observation_id, fixture_id, home_team, away_team, "
                "competition_name, country, competition_type, kickoff_at, provider_status, "
                "source, observed_at, persisted_at FROM fixture_observations "
                "WHERE fixture_id = %s AND observed_at = %s AND source = %s",
                (fixture.fixture_id, observed, fixture.provider),
            )
            row = cursor.fetchone()
            if row is None:
                raise FixturePersistenceConflictError("fixture observation could not be resolved")
            observation = self._row_to_observation(row)
            expected_observation = (
                observation_id,
                fixture.fixture_id,
                fixture.home_team,
                fixture.away_team,
                fixture.competition_name,
                fixture.country,
                fixture.competition_type,
                kickoff,
                fixture.status,
                fixture.provider,
                observed,
            )
            actual_observation = (
                observation.fixture_observation_id,
                observation.fixture_id,
                observation.home_team,
                observation.away_team,
                observation.competition_name,
                observation.country,
                observation.competition_type,
                observation.kickoff_at,
                observation.provider_status,
                observation.source,
                observation.observed_at,
            )
            if actual_observation != expected_observation:
                raise FixturePersistenceConflictError("conflicting fixture observation replay")
            return PersistedFixture(identity, observation)

    def get(self, fixture_id: str) -> PersistedFixture | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT fixture_id, provider, provider_fixture_id, league_id, season, "
                "provider_home_team_id, provider_away_team_id, created_at FROM fixtures "
                "WHERE fixture_id = %s",
                (fixture_id,),
            )
            identity_row = cursor.fetchone()
            if identity_row is None:
                return None
            cursor.execute(
                "SELECT fixture_observation_id, fixture_id, home_team, away_team, "
                "competition_name, country, competition_type, kickoff_at, provider_status, "
                "source, observed_at, persisted_at FROM fixture_observations "
                "WHERE fixture_id = %s ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
                (fixture_id,),
            )
            observation_row = cursor.fetchone()
            if observation_row is None:
                raise FixturePersistenceConflictError("durable fixture has no observation")
            return PersistedFixture(
                self._row_to_identity(identity_row), self._row_to_observation(observation_row)
            )

    def get_observation(self, fixture_observation_id: str) -> PersistedFixture | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT f.fixture_id, f.provider, f.provider_fixture_id, f.league_id, f.season, "
                "f.provider_home_team_id, f.provider_away_team_id, f.created_at, "
                "o.fixture_observation_id, o.fixture_id, o.home_team, o.away_team, "
                "o.competition_name, o.country, o.competition_type, o.kickoff_at, "
                "o.provider_status, o.source, o.observed_at, o.persisted_at "
                "FROM fixture_observations o JOIN fixtures f ON f.fixture_id = o.fixture_id "
                "WHERE o.fixture_observation_id = %s",
                (fixture_observation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return PersistedFixture(
                self._row_to_identity(row[:8]), self._row_to_observation(row[8:])
            )

    @staticmethod
    def _row_to_identity(row: tuple[Any, ...]) -> FixtureIdentityRecord:
        return FixtureIdentityRecord(*row)

    @staticmethod
    def _row_to_observation(row: tuple[Any, ...]) -> FixtureObservation:
        return FixtureObservation(*row)
