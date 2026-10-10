"""Offline safety checks for the read-only PostgreSQL diagnostic snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from scripts.postgres_health_snapshot import ROW_LIMITS, SQL, build_snapshot


def _groups() -> dict[str, list[dict[str, object]]]:
    return {
        name: [] for name in SQL
    }


def test_snapshot_encodes_statistics_without_queries_or_credentials() -> None:
    readings = _groups()
    readings["wal_statistics"] = [{
        "wal_bytes": Decimal("123456789.1"),
        "wal_records": 20,
        "stats_reset": datetime(2026, 10, 1, tzinfo=UTC),
    }]
    readings["connection_states"] = [{
        "state": "active",
        "wait_type": "none",
        "connections": 2,
    }]
    snapshot = build_snapshot(
        readings, captured_at=datetime(2026, 10, 11, 1, 0, tzinfo=UTC)
    )
    assert snapshot["observations"]["wal_statistics"][0]["wal_bytes"] == "123456789.1"
    assert snapshot["observations"]["wal_statistics"][0]["stats_reset"] == (
        "2026-10-01T00:00:00+00:00"
    )
    assert snapshot["observations"]["connection_states"][0]["connections"] == 2
    assert "backup inventory" in snapshot["source"]
    assert "query" not in str(snapshot["observations"])


def test_snapshot_requires_every_section_and_bounds_result_count() -> None:
    groups = _groups()
    groups.pop("wal_statistics")
    with pytest.raises(ValueError, match="missing"):
        build_snapshot(groups, captured_at=datetime.now(UTC))

    groups = _groups()
    groups["server"] = [{"version": "18"}] * (ROW_LIMITS["server"] + 1)
    with pytest.raises(ValueError, match="row count"):
        build_snapshot(groups, captured_at=datetime.now(UTC))


def test_sql_queries_are_read_only_and_bounded() -> None:
    assert set(SQL) == set(ROW_LIMITS)
    assert all(query.lstrip().upper().startswith("SELECT") for query in SQL.values())
    forbidden = (
        "INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP ",
        "CREATE ", "GRANT ", "REVOKE ", "PG_TERMINATE_BACKEND",
        "PG_CANCEL_BACKEND", "PG_SLEEP(", "EXPLAIN ANALYZE",
    )
    for query in SQL.values():
        upper = query.upper()
        assert not any(keyword in upper for keyword in forbidden)
        assert "QUERY_TEXT" not in upper
    assert "pg_stat_checkpointer" in SQL["checkpoint_statistics"]
    assert "pg_stat_wal" in SQL["wal_statistics"]
    assert "pg_stat_activity" in SQL["connection_states"]
    assert "LIMIT 12" in SQL["largest_tables"]
