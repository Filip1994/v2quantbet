from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.bookmaker_policy import API_FOOTBALL_BOOKMAKERS
from h2h.domain.fixture import Fixture
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.pick_monitoring import ClosingOutcome, MonitoringState, OddsLifecyclePolicy
from h2h.persistence.postgres_daily_bulletin import PostgreSQLDailyBulletinRepository
from h2h.persistence.postgres_fixtures import PostgreSQLFixtureRepository
from h2h.persistence.postgres_pick_monitoring import PostgreSQLPickMonitoringRepository
from h2h.persistence.postgres_pick_registration import PostgreSQLPickRegistrationRepository
from h2h.persistence.postgres_quote_history import PostgreSQLQuoteHistoryRepository
from h2h.persistence.migrations import apply_migrations
from h2h.read_models.daily_bulletin import DailyBulletin
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from tests.integration.test_postgres_task10_integration import (
    DurableCandidate,
    _candidate,
    _cleanup,
    _migrate,
    _policy,
)


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
LIFECYCLE = OddsLifecyclePolicy(300, 600, 900)
MIGRATION_DIR = Path(__file__).parents[2] / "migrations"


def _registered(candidate: DurableCandidate, account: str):
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    configured = _policy(account, maximum_quote_age_seconds=3600)
    now = datetime.now(UTC)
    repository.bootstrap_bankroll(configured, occurred_at=now)
    return repository.register(
        candidate.evaluation_id,
        f"request-{account}",
        configured,
        decided_at=now,
    ).pick


def test_fresh_schema_migrates_in_order_through_latest() -> None:
    assert DATABASE_URL is not None
    schema = "task11_" + uuid4().hex
    with psycopg.connect(DATABASE_URL) as admin, admin.cursor() as cursor:
        cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(schema)))
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                psycopg.sql.SQL("SET search_path TO {}").format(psycopg.sql.Identifier(schema))
            )
            applied = apply_migrations(connection, MIGRATION_DIR)
            assert applied == tuple(path.name for path in sorted(MIGRATION_DIR.glob("*.sql")))
            assert applied[-1] == "018_flush_opportunity_operational_backoff.sql"
        with psycopg.connect(DATABASE_URL) as inspection:
            inspection.execute(
                psycopg.sql.SQL("SET search_path TO {}").format(psycopg.sql.Identifier(schema))
            )
            row = inspection.execute("SELECT to_regclass('pick_closing_finalizations')").fetchone()
            assert row[0] == "pick_closing_finalizations"
            row = inspection.execute("SELECT to_regclass('pick_settlement_events')").fetchone()
            assert row[0] == "pick_settlement_events"
    finally:
        with psycopg.connect(DATABASE_URL) as admin, admin.cursor() as cursor:
            cursor.execute(
                psycopg.sql.SQL("DROP SCHEMA {} CASCADE").format(psycopg.sql.Identifier(schema))
            )


def _fixture_cutoff(candidate: DurableCandidate) -> datetime:
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT kickoff_at FROM fixture_observations WHERE fixture_id = %s "
            "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
            (candidate.fixture_id,),
        )
        return cursor.fetchone()[0]


def _selected_context(candidate: DurableCandidate):
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT e.selected_series_id, e.bookmaker_id, e.market, e.selected_selection, e.source "
            "FROM value_evaluations e WHERE e.evaluation_id = %s",
            (candidate.evaluation_id,),
        )
        return cursor.fetchone()


def _ingest_selected(
    candidate: DurableCandidate,
    *,
    observed_at: datetime,
    captured_at: datetime,
    odd: float,
    source: str = "api-football",
) -> str:
    series_id, bookmaker_id, market, selection, _ = _selected_context(candidate)
    repository = PostgreSQLQuoteHistoryRepository(database_url=DATABASE_URL)
    QuoteHistoryIngestionService(repository, capture_clock=lambda: captured_at).ingest(
        (
            CanonicalQuote(
                candidate.fixture_id,
                bookmaker_id,
                API_FOOTBALL_BOOKMAKERS[bookmaker_id],
                Market(market),
                Selection(selection),
                odd,
                observed_at,
                source,
            ),
        )
    )
    snapshots = repository.snapshots_for_series(series_id)
    return next(
        snapshot.snapshot_id
        for snapshot in snapshots
        if snapshot.observed_at == observed_at and snapshot.source == source
    )


def _reschedule(
    candidate: DurableCandidate, *, kickoff_at: datetime, observed_at: datetime
) -> None:
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT f.provider_fixture_id, f.league_id, f.season, f.provider_home_team_id, "
            "f.provider_away_team_id, o.home_team, o.away_team, o.competition_name, o.country, "
            "o.competition_type FROM fixtures f JOIN LATERAL (SELECT * FROM fixture_observations "
            "WHERE fixture_id = f.fixture_id ORDER BY observed_at DESC LIMIT 1) o ON TRUE "
            "WHERE f.fixture_id = %s",
            (candidate.fixture_id,),
        )
        row = cursor.fetchone()
    PostgreSQLFixtureRepository(database_url=DATABASE_URL).record_discovery(
        Fixture(
            fixture_id=candidate.fixture_id,
            home_team=row[5],
            away_team=row[6],
            competition_id=row[1],
            competition_name=row[7],
            country=row[8],
            kickoff_at=kickoff_at,
            competition_type=row[9],
            season=row[2],
            status="NS",
            provider="api-football",
            provider_fixture_id=row[0],
            provider_home_team_id=row[3],
            provider_away_team_id=row[4],
        ),
        observed_at=observed_at,
    )


def test_opening_current_closing_markers_bulletin_and_late_quote_freeze() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task11-{uuid4()}"
    pick = _registered(candidate, account)
    assert pick is not None
    repository = PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL)
    cutoff = _fixture_cutoff(candidate)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            starts = list(
                executor.map(
                    lambda _: PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL).start(
                        pick.pick_id, LIFECYCLE, started_at=pick.registered_at
                    ),
                    range(2),
                )
            )
        assert starts[0] == starts[1]

        opening_id = _ingest_selected(
            candidate,
            observed_at=cutoff - timedelta(minutes=40),
            captured_at=cutoff - timedelta(minutes=50),
            odd=1.91,
        )
        _ingest_selected(
            candidate,
            observed_at=cutoff - timedelta(minutes=45),
            captured_at=cutoff - timedelta(minutes=30),
            odd=1.95,
        )
        closing_id = _ingest_selected(
            candidate,
            observed_at=cutoff - timedelta(minutes=5),
            captured_at=cutoff - timedelta(minutes=5),
            odd=2.10,
        )

        before = repository.read_lifecycle(pick.pick_id, as_of=cutoff - timedelta(minutes=1))
        assert before.opening.snapshot_id == opening_id
        assert before.entry.snapshot_id == pick.entry_snapshot_id
        assert before.current.snapshot_id == closing_id
        assert before.current.freshness.value == "FRESH"
        assert before.closing is None

        with ThreadPoolExecutor(max_workers=2) as executor:
            closes = list(
                executor.map(
                    lambda _: PostgreSQLPickMonitoringRepository(
                        database_url=DATABASE_URL
                    ).finalize(pick.pick_id, finalized_at=cutoff),
                    range(2),
                )
            )
        assert closes[0] == closes[1]
        assert closes[0].outcome is ClosingOutcome.CAPTURED
        assert closes[0].closing_snapshot_id == closing_id

        _ingest_selected(
            candidate,
            observed_at=cutoff - timedelta(minutes=1),
            captured_at=cutoff + timedelta(minutes=1),
            odd=2.25,
        )
        # Explicit historical backfill after finalization carries pre-cutoff timestamps.
        # It remains history but cannot move frozen Current or immutable Closing.
        _ingest_selected(
            candidate,
            observed_at=cutoff - timedelta(minutes=2),
            captured_at=cutoff - timedelta(minutes=2),
            odd=2.30,
            source="api-football",
        )
        after = repository.read_lifecycle(pick.pick_id, as_of=cutoff + timedelta(hours=1))
        assert after.state is MonitoringState.CLOSED_FOR_ODDS
        assert after.current.snapshot_id == closing_id
        assert after.closing.snapshot_id == closing_id
        assert after.markers[closing_id] == ("CURRENT", "CLOSE")
        assert after.markers[pick.entry_snapshot_id] == ("ENTRY",)

        bulletin = DailyBulletin(
            PostgreSQLDailyBulletinRepository(repository), ZoneInfo("Europe/Belgrade")
        )
        entries = bulletin.execute(
            pick.registered_at.astimezone(ZoneInfo("Europe/Belgrade")).date(),
            as_of=cutoff + timedelta(hours=1),
        )
        assert all(item.pick_id != pick.pick_id for item in entries)
    finally:
        _cleanup(account, (candidate,))


@pytest.mark.parametrize("age_minutes", [15, 16, 180])
def test_closing_uses_last_valid_prekickoff_candidate_regardless_of_age(age_minutes) -> None:
    _migrate()
    candidate = _candidate()
    account = f"task11-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL)
    cutoff = _fixture_cutoff(candidate)
    try:
        repository.start(pick.pick_id, LIFECYCLE, started_at=pick.registered_at)
        candidate_id = _ingest_selected(
            candidate,
            observed_at=cutoff - timedelta(minutes=age_minutes),
            captured_at=cutoff - timedelta(minutes=age_minutes),
            odd=2.05,
        )
        current = repository.read_lifecycle(
            pick.pick_id, as_of=cutoff - timedelta(seconds=1)
        ).current
        assert current is not None
        assert current.freshness.value == "STALE"
        result = repository.finalize(pick.pick_id, finalized_at=cutoff)
        assert result.outcome is ClosingOutcome.CAPTURED
        assert result.candidate_snapshot_id == candidate_id
        assert result.closing_snapshot_id == candidate_id
    finally:
        _cleanup(account, (candidate,))


def test_no_valid_quote_and_source_mismatch_remain_absent() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task11-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL)
    cutoff = _fixture_cutoff(candidate)
    try:
        repository.start(pick.pick_id, LIFECYCLE, started_at=pick.registered_at)
        _ingest_selected(
            candidate,
            observed_at=cutoff - timedelta(minutes=5),
            captured_at=cutoff - timedelta(minutes=5),
            odd=2.2,
            source="replacement-source",
        )
        result = repository.finalize(pick.pick_id, finalized_at=cutoff)
        assert result.outcome is ClosingOutcome.NO_VALID_QUOTE
        assert result.candidate_snapshot_id is None
        assert result.closing_snapshot_id is None
    finally:
        _cleanup(account, (candidate,))


def test_reschedule_before_finalization_moves_cutoff_but_after_close_does_not() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task11-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL)
    original_cutoff = _fixture_cutoff(candidate)
    moved_cutoff = original_cutoff + timedelta(hours=1)
    try:
        repository.start(pick.pick_id, LIFECYCLE, started_at=pick.registered_at)
        _reschedule(
            candidate,
            kickoff_at=moved_cutoff,
            observed_at=pick.registered_at + timedelta(minutes=1),
        )
        moved_quote = _ingest_selected(
            candidate,
            observed_at=moved_cutoff - timedelta(minutes=5),
            captured_at=moved_cutoff - timedelta(minutes=5),
            odd=2.15,
        )
        closed = repository.finalize(pick.pick_id, finalized_at=moved_cutoff)
        assert closed.cutoff_at == moved_cutoff
        assert closed.closing_snapshot_id == moved_quote

        _reschedule(
            candidate,
            kickoff_at=moved_cutoff + timedelta(hours=1),
            observed_at=moved_cutoff + timedelta(minutes=1),
        )
        replay = repository.finalize(pick.pick_id, finalized_at=moved_cutoff + timedelta(hours=1))
        assert replay == closed
        assert replay.cutoff_at == moved_cutoff
    finally:
        _cleanup(account, (candidate,))


def test_quote_insert_and_finalization_share_series_serialization() -> None:
    _migrate()
    candidate = _candidate()
    account = f"task11-{uuid4()}"
    pick = _registered(candidate, account)
    repository = PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL)
    cutoff = _fixture_cutoff(candidate)
    barrier = Barrier(2)
    try:
        repository.start(pick.pick_id, LIFECYCLE, started_at=pick.registered_at)

        def ingest():
            barrier.wait()
            return _ingest_selected(
                candidate,
                observed_at=cutoff - timedelta(minutes=4),
                captured_at=cutoff - timedelta(minutes=4),
                odd=2.18,
            )

        def finalize():
            barrier.wait()
            return PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL).finalize(
                pick.pick_id, finalized_at=cutoff
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            inserted_future = executor.submit(ingest)
            finalized_future = executor.submit(finalize)
            inserted_id = inserted_future.result()
            finalized = finalized_future.result()

        replay = repository.finalize(pick.pick_id, finalized_at=cutoff + timedelta(minutes=1))
        assert replay == finalized
        lifecycle = repository.read_lifecycle(pick.pick_id, as_of=cutoff + timedelta(hours=1))
        assert lifecycle.closing_outcome is finalized.outcome
        if finalized.candidate_snapshot_id is None:
            assert lifecycle.current is None
        else:
            assert lifecycle.current.snapshot_id == finalized.candidate_snapshot_id
        if finalized.closing_snapshot_id == inserted_id:
            assert lifecycle.closing.snapshot_id == inserted_id
        else:
            assert lifecycle.closing is None or lifecycle.closing.snapshot_id != inserted_id
    finally:
        _cleanup(account, (candidate,))
