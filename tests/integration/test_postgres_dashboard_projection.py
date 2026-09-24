from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

psycopg = pytest.importorskip("psycopg")

from h2h.api.dashboard import DashboardService
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository


DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MIGRATION_DIR = Path(__file__).parents[2] / "migrations"


def test_dashboard_pick_projection_query_is_valid_on_current_schema() -> None:
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        apply_migrations(connection, MIGRATION_DIR)

    service = DashboardService(
        SimpleNamespace(runtime=PostgreSQLRuntimeRepository(database_url=DATABASE_URL))
    )

    assert isinstance(service._picks(), list)
