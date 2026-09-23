from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.final_quote import FinalQuoteStatus
from h2h.domain.pick_decision import DecisionOutcome
from h2h.persistence.postgres_pick_registration import PostgreSQLPickRegistrationRepository
from h2h.persistence.postgres_daily_bulletin import PostgreSQLDailyBulletinRepository
from h2h.persistence.postgres_pick_monitoring import PostgreSQLPickMonitoringRepository
from h2h.read_models.daily_bulletin import DailyBulletin
from tests.integration.test_postgres_task10_integration import (
    DATABASE_URL,
    _candidate,
    _cleanup,
    _migrate,
    _policy,
)


pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def test_final_verification_is_replay_safe_and_links_approved_decision() -> None:
    _migrate()
    candidate = _candidate()
    account = "final-publication-integration"
    policy = _policy(account, maximum_quote_age_seconds=1)
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    now = datetime.now(UTC)
    try:
        repository.bootstrap_bankroll(policy, occurred_at=now)
        first = repository.begin_final_quote_verification(candidate.evaluation_id, requested_at=now)
        replay = repository.begin_final_quote_verification(
            candidate.evaluation_id, requested_at=now
        )
        assert first.should_fetch is True
        assert replay.should_fetch is False

        ready = repository.complete_final_quote_verification(
            first.verification_id,
            candidate.evaluation_id,
            captured_at=now,
            quote_age_seconds=3600,
            snapshot_ids=candidate.snapshot_ids,
            stale_quote=True,
            minimum_playable_odds=1.7,
            decided_at=now,
        )
        assert ready.status is FinalQuoteStatus.READY
        result = repository.register(
            candidate.evaluation_id,
            "final-publication-request",
            policy,
            decided_at=now,
            final_quote_verification_id=ready.verification_id,
        )
        assert result.decision.outcome is DecisionOutcome.APPROVED
        assert result.pick is not None

        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT stale_quote, warning_codes, quote_age_seconds, final_odd, "
                "minimum_playable_odds FROM final_quote_verifications "
                "WHERE verification_id = %s",
                (ready.verification_id,),
            )
            row = cursor.fetchone()
            assert row[:3] == (True, ["STALE_QUOTE_WARNING"], 3600.0)
            assert float(row[3]) > 1
            assert float(row[4]) == 1.7
    finally:
        _cleanup(account, (candidate,))


def test_daily_bulletin_snapshots_actionable_prior_day_pick_idempotently() -> None:
    _migrate()
    candidate = _candidate()
    account = "daily-bulletin-integration"
    policy = _policy(account)
    repository = PostgreSQLPickRegistrationRepository(database_url=DATABASE_URL)
    now = datetime.now(UTC)
    try:
        repository.bootstrap_bankroll(policy, occurred_at=now)
        pick = repository.register(
            candidate.evaluation_id,
            "daily-bulletin-registration",
            policy,
            decided_at=now,
        ).pick
        assert pick is not None
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE registered_picks SET registered_at = %s WHERE pick_id = %s",
                (now - timedelta(days=1), pick.pick_id),
            )
        bulletin = DailyBulletin(
            PostgreSQLDailyBulletinRepository(
                PostgreSQLPickMonitoringRepository(database_url=DATABASE_URL)
            ),
            ZoneInfo("Europe/Belgrade"),
        )
        day = now.astimezone(ZoneInfo("Europe/Belgrade")).date()
        entries = bulletin.execute(day, as_of=now, horizon=timedelta(hours=72))
        assert [entry.pick_id for entry in entries] == [pick.pick_id]
        first = bulletin.generate(day, as_of=now, horizon=timedelta(hours=72))
        replay = bulletin.generate(
            day, as_of=now + timedelta(minutes=1), horizon=timedelta(hours=72)
        )
        assert replay.bulletin_id == first.bulletin_id
        assert first.created is True
        assert replay.created is False
        assert first.pick_ids == (pick.pick_id,)
    finally:
        _cleanup(account, (candidate,))
