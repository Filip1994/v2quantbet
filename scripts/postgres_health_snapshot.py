"""Bounded read-only PostgreSQL 18 health snapshot for QuantBet.

Run in a trusted environment with an existing restricted DB credential:
    DATABASE_URL=... python scripts/postgres_health_snapshot.py

No schema changes, EXPLAIN ANALYZE, pg_terminate_backend, or raw query text.
Counters are cumulative since their own stats_reset, NOT per-minute rates.
A second snapshot is required to derive a WAL/write rate; this does not
confirm Railway volume backups or isolate why platform RSS is near its limit.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

SQL: dict[str, str] = {
    "server": """
        SELECT current_setting('server_version') AS version,
               pg_postmaster_start_time() AS postmaster_start
    """,
    "memory_settings": """
        SELECT name, setting, unit
        FROM pg_settings
        WHERE name IN (
            'shared_buffers', 'work_mem', 'maintenance_work_mem',
            'autovacuum_work_mem', 'max_connections',
            'effective_cache_size', 'temp_buffers',
            'max_wal_size', 'min_wal_size', 'checkpoint_timeout',
            'max_parallel_workers_per_gather', 'max_parallel_workers'
        )
        ORDER BY name
    """,
    "connection_states": """
        SELECT COALESCE(state, 'background/unknown') AS state,
               COALESCE(wait_event_type, 'none') AS wait_type,
               COUNT(*) AS connections
        FROM pg_stat_activity
        GROUP BY state, wait_event_type
        ORDER BY connections DESC, state, wait_type
    """,
    "lock_counts": """
        SELECT locktype, mode, granted, COUNT(*) AS lock_count
        FROM pg_locks
        GROUP BY locktype, mode, granted
        ORDER BY lock_count DESC, locktype, mode
        LIMIT 20
    """,
    "database_statistics": """
        SELECT numbackends, xact_commit, xact_rollback,
               blks_read, blks_hit, temp_files, temp_bytes, deadlocks,
               tup_inserted, tup_updated, tup_deleted, stats_reset
        FROM pg_stat_database
        WHERE datname = current_database()
    """,
    "wal_statistics": """
        SELECT wal_records, wal_fpi, wal_bytes,
               wal_buffers_full, stats_reset
        FROM pg_stat_wal
    """,
    "checkpoint_statistics": """
        SELECT num_timed, num_requested, num_done,
               write_time, sync_time, buffers_written, stats_reset
        FROM pg_stat_checkpointer
    """,
    "largest_tables": """
        SELECT relname, pg_total_relation_size(relid) AS total_bytes,
               n_live_tup, n_dead_tup,
               last_autovacuum, last_autoanalyze
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(relid) DESC
        LIMIT 12
    """,
    "extensions": """
        SELECT EXISTS (
            SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
        ) AS pg_stat_statements_available
    """,
}

ROW_LIMITS = {
    "server": 1,
    "memory_settings": 12,
    "connection_states": 30,
    "lock_counts": 20,
    "database_statistics": 1,
    "wal_statistics": 1,
    "checkpoint_statistics": 1,
    "largest_tables": 12,
    "extensions": 1,
}


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def build_snapshot(
    observations: dict[str, list[dict[str, Any]]],
    *,
    captured_at: datetime,
) -> dict[str, Any]:
    """Produce aggregate diagnostics without raw SQL text or client identities."""
    missing = SQL.keys() - observations.keys()
    if missing:
        raise ValueError("missing PostgreSQL observation groups")
    for group, rows in observations.items():
        if group not in SQL or len(rows) > ROW_LIMITS[group]:
            raise ValueError("unexpected observation group or row count")
    return {
        "captured_at": captured_at.astimezone(UTC).isoformat(),
        "source": "PostgreSQL read-only statistics; not Railway backup inventory",
        "observations": {
            group: [
                {name: _encode(value) for name, value in row.items()}
                for row in observations[group]
            ]
            for group in SQL
        },
        "interpretation_limits": [
            "WAL and checkpoint counters are cumulative since their own stats_reset.",
            "Compare two samples with matching stats_reset to calculate write rates.",
            "Shared buffers and connection memory cannot be inferred from Railway RSS alone.",
            "A checkpoint write_time near checkpoint_timeout is not an I/O failure by itself.",
            "Only Railway backup inventory and isolated restore prove recoverability.",
            "No query text, credentials, IP addresses or registered pick IDs are returned.",
        ],
    }


def read_snapshot(database_url: str) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(
        database_url,
        row_factory=dict_row,
        autocommit=True,
        options="-c default_transaction_read_only=on -c statement_timeout=10000",
    ) as connection:
        with connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            readings: dict[str, list[dict[str, Any]]] = {}
            with connection.cursor() as cursor:
                for group, query in SQL.items():
                    cursor.execute(query)
                    readings[group] = [
                        dict(row) for row in cursor.fetchmany(ROW_LIMITS[group] + 1)
                    ]
            return build_snapshot(readings, captured_at=datetime.now(UTC))


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required but must never be printed")
    print(json.dumps(read_snapshot(database_url), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
