"""PostgreSQL catalog and read-through access for cold archive batches."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

from h2h.archive.object_store import S3ObjectStore


class ColdArchiveCatalog:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        connect: Callable[[], Any] | None = None,
    ) -> None:
        self._database_url = database_url or os.getenv("DATABASE_URL", "").strip()
        self._connect_factory = connect
        if not self._database_url and connect is None:
            raise ValueError("DATABASE_URL is required")

    def connect(self) -> Any:
        if self._connect_factory is not None:
            return self._connect_factory()
        import psycopg

        return psycopg.connect(self._database_url)

    def table_sizes(self, *, limit: int = 30) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname AS table_name, "
                "pg_total_relation_size(relid) AS total_bytes, "
                "pg_relation_size(relid) AS heap_bytes, "
                "pg_indexes_size(relid) AS index_bytes, "
                "n_live_tup::BIGINT AS live_rows, n_dead_tup::BIGINT AS dead_rows "
                "FROM pg_stat_user_tables "
                "ORDER BY pg_total_relation_size(relid) DESC, relname LIMIT %s",
                (limit,),
            )
            columns = tuple(item.name for item in cursor.description)
            return tuple(
                dict(zip(columns, row, strict=True)) for row in cursor.fetchall()
            )

    def market_observation_stats(self) -> tuple[dict[str, Any], ...]:
        """Return planner statistics without scanning the multi-GB market table."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT attname, avg_width, n_distinct, "
                "most_common_vals::text AS most_common_vals, "
                "most_common_freqs::text AS most_common_freqs, "
                "histogram_bounds::text AS histogram_bounds "
                "FROM pg_stats "
                "WHERE schemaname = 'public' "
                "AND tablename = 'quantlab_market_observations' "
                "AND attname = ANY(%s) ORDER BY attname",
                (
                    [
                        "captured_at",
                        "fixture_id",
                        "lab_owner",
                        "provider_bet_id",
                        "provider_updated_at",
                        "raw_payload",
                    ],
                ),
            )
            columns = tuple(item.name for item in cursor.description)
            return tuple(
                dict(zip(columns, row, strict=True)) for row in cursor.fetchall()
            )

    def register_verified_batch(
        self,
        *,
        dataset: str,
        object_key: str,
        row_count: int,
        compressed_bytes: int,
        content_sha256: str,
        verified_at: datetime,
        min_recorded_at: datetime | None = None,
        max_recorded_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not dataset.strip():
            raise ValueError("dataset must not be empty")
        if not object_key.strip():
            raise ValueError("object_key must not be empty")
        identity = {
            "dataset": dataset,
            "object_key": object_key,
            "content_sha256": content_sha256,
        }
        batch_id = "cold-archive-v1:" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO cold_archive_batches ("
                "archive_batch_id, dataset, object_key, format, min_recorded_at, "
                "max_recorded_at, row_count, compressed_bytes, content_sha256, "
                "verified_at, metadata"
                ") VALUES (%s, %s, %s, 'jsonl+gzip', %s, %s, %s, %s, %s, %s, %s::jsonb) "
                "ON CONFLICT (archive_batch_id) DO UPDATE SET "
                "verified_at = EXCLUDED.verified_at, metadata = EXCLUDED.metadata",
                (
                    batch_id,
                    dataset,
                    object_key,
                    min_recorded_at,
                    max_recorded_at,
                    row_count,
                    compressed_bytes,
                    content_sha256,
                    verified_at,
                    json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
                ),
            )
        return batch_id

    def list_batches(
        self,
        dataset: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[dict[str, Any], ...]:
        clauses = ["dataset = %s"]
        params: list[Any] = [dataset]
        if start is not None:
            clauses.append("(max_recorded_at IS NULL OR max_recorded_at >= %s)")
            params.append(start)
        if end is not None:
            clauses.append("(min_recorded_at IS NULL OR min_recorded_at <= %s)")
            params.append(end)
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT archive_batch_id, dataset, object_key, format, min_recorded_at, "
                "max_recorded_at, row_count, compressed_bytes, content_sha256, created_at, "
                "verified_at, deleted_from_hot_at, metadata "
                "FROM cold_archive_batches WHERE "
                + " AND ".join(clauses)
                + " ORDER BY min_recorded_at NULLS FIRST, created_at, archive_batch_id",
                tuple(params),
            )
            columns = tuple(item.name for item in cursor.description)
            rows = [
                dict(zip(columns, row, strict=True)) for row in cursor.fetchall()
            ]
        for row in rows:
            if isinstance(row.get("metadata"), str):
                row["metadata"] = json.loads(row["metadata"])
        return tuple(rows)


class ColdArchiveReader:
    """Research-facing reader over immutable archived JSONL batches."""

    def __init__(self, catalog: ColdArchiveCatalog, store: S3ObjectStore) -> None:
        self.catalog = catalog
        self.store = store

    def iter_rows(
        self,
        dataset: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Iterator[dict[str, Any]]:
        for batch in self.catalog.list_batches(dataset, start=start, end=end):
            yield from self.store.get_jsonl_gzip(str(batch["object_key"]))

    def rows(
        self,
        dataset: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[dict[str, Any], ...]:
        return tuple(self.iter_rows(dataset, start=start, end=end))
