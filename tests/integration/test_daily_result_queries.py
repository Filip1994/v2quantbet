from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.domain.settlement import ResultSettlementPolicy
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="test PostgreSQL is required")


def test_daily_snapshot_and_claim_do_not_touch_completed_quarantined_or_unselected_fixtures():
    now = datetime(2026, 11, 5, 7, tzinfo=UTC)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "CREATE TEMP TABLE fixture_result_acquisition_states "
            "(fixture_id text, phase text, next_check_at timestamptz, "
            "lease_expires_at timestamptz, updated_at timestamptz, version integer)"
        )
        for fixture_id, phase, due, lease in (
            ("due-a", "WAITING", now, None),
            ("due-b", "POLLING", now, None),
            ("complete", "COMPLETE", now, None),
            ("quarantined", "QUARANTINED", now, None),
            ("future", "WAITING", now + timedelta(days=1), None),
            ("leased", "WAITING", now, now + timedelta(minutes=1)),
        ):
            connection.execute(
                "INSERT INTO fixture_result_acquisition_states VALUES (%s,%s,%s,%s,%s,1)",
                (fixture_id, phase, due, lease, now - timedelta(days=1)),
            )
        repository = PostgreSQLResultSettlementRepository(
            ResultSettlementPolicy(), connect=lambda: nullcontext(connection)
        )
        assert repository.due_fixture_ids(as_of=now) == ("due-a", "due-b")
        assert repository.claim_due(
            claimed_at=now, limit=20, fixture_ids=("due-b",)
        ) == ("due-b",)
        assert repository.due_fixture_ids(as_of=now) == ("due-a",)
        assert connection.execute(
            "SELECT fixture_id FROM fixture_result_acquisition_states WHERE version=2"
        ).fetchall() == [("due-b",)]


def test_persisting_daily_deadline_preserves_attempt_marker_and_counts():
    now = datetime(2026, 11, 5, 8, tzinfo=UTC)
    with psycopg.connect(DATABASE_URL) as connection:
        ddl = (Path(__file__).parents[2] / "migrations/008_production_runtime.sql").read_text()
        connection.execute(ddl.split("CREATE TABLE production_item_failures")[0].replace(
            "CREATE TABLE production_worker_status", "CREATE TEMP TABLE production_worker_status"
        ))
        repository = PostgreSQLRuntimeRepository(connect=lambda: nullcontext(connection))
        repository.worker_started("results", "first", at=now)
        repository.worker_scheduled(
            "results", "restarted", at=now + timedelta(hours=1),
            next_due_at=now + timedelta(hours=23),
        )
        status, = repository.worker_statuses()
        assert status.last_started_at == now
        assert status.cycle_count == 1
        assert status.next_due_at == now + timedelta(hours=23)
        assert status.instance_id == "restarted"
