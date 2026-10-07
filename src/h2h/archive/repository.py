"""PostgreSQL catalog and read-through access for cold archive batches."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from h2h.archive.object_store import S3ObjectStore


def _row_dicts(cursor: Any) -> tuple[dict[str, Any], ...]:
    columns = tuple(item.name for item in cursor.description)
    return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


class ColdArchiveCatalog:
    _RUN_LOCK_KEYS = (0x51424152, 1)  # QBAR lifecycle, shared across cron containers.

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

    @contextmanager
    def exclusive_run(self) -> Iterator[bool]:
        """Serialize cron runs without holding an open database transaction."""
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", self._RUN_LOCK_KEYS)
                acquired = bool(cursor.fetchone()[0])
            connection.commit()
            try:
                yield acquired
            finally:
                if acquired:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_unlock(%s, %s)", self._RUN_LOCK_KEYS
                        )
                        released = bool(cursor.fetchone()[0])
                    connection.commit()
                    if not released:
                        raise RuntimeError("archive lifecycle advisory lock was lost")

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
            return _row_dicts(cursor)

    def market_observation_stats(self) -> tuple[dict[str, Any], ...]:
        """Return compact planner statistics without scanning the multi-GB market table."""
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT attname, avg_width, n_distinct "
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
            return _row_dicts(cursor)

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

    def mark_deleted_from_hot(
        self,
        archive_batch_id: str,
        *,
        deleted_rows: int,
        selected_rows: int,
        deleted_at: datetime | None = None,
    ) -> None:
        timestamp = deleted_at or datetime.now(UTC)
        metadata = {
            "selected_rows": selected_rows,
            "deleted_rows": deleted_rows,
            "retained_hot_rows": max(selected_rows - deleted_rows, 0),
        }
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE cold_archive_batches "
                "SET deleted_from_hot_at = COALESCE(deleted_from_hot_at, %s), "
                "metadata = metadata || %s::jsonb "
                "WHERE archive_batch_id = %s",
                (
                    timestamp,
                    json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                    archive_batch_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("archive batch disappeared before hot-delete marking")

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
            rows = list(_row_dicts(cursor))
        for row in rows:
            if isinstance(row.get("metadata"), str):
                row["metadata"] = json.loads(row["metadata"])
        return tuple(rows)

    @staticmethod
    def _market_unreferenced_sql(alias: str = "m") -> str:
        return (
            f"NOT EXISTS (SELECT 1 FROM quantlab_goal_decisions d "
            f"WHERE d.selected_observation_id = {alias}.market_observation_id "
            f"OR d.companion_observation_id = {alias}.market_observation_id) "
            f"AND NOT EXISTS (SELECT 1 FROM quantlab_context_market_decisions d "
            f"WHERE d.selected_observation_id = {alias}.market_observation_id "
            f"OR d.companion_observation_id = {alias}.market_observation_id "
            f"OR d.reference_observation_id = {alias}.market_observation_id "
            f"OR d.reference_companion_observation_id = {alias}.market_observation_id) "
            f"AND NOT EXISTS (SELECT 1 FROM quantlab_goal_picks p "
            f"WHERE p.selected_observation_id = {alias}.market_observation_id "
            f"OR p.companion_observation_id = {alias}.market_observation_id) "
            f"AND NOT EXISTS (SELECT 1 FROM quantlab_h2h_decisions d "
            f"WHERE d.selected_observation_id = {alias}.market_observation_id "
            f"OR d.companion_observation_id = {alias}.market_observation_id)"
        )

    def market_archive_candidates(
        self,
        *,
        cutoff: datetime,
        limit: int,
        after_id: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        predicate = self._market_unreferenced_sql("m")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT m.market_observation_id, m.fixture_id, m.provider_fixture_id, "
                "m.bookmaker_id, m.bookmaker_name, m.provider_bet_id, m.provider_bet_name, "
                "m.raw_selection, m.parsed_line, m.odds, m.provider_updated_at, "
                "m.captured_at, m.lab_owner, m.classifier_version, m.raw_payload "
                "FROM quantlab_market_observations m "
                "WHERE m.captured_at < %s "
                + ("AND m.market_observation_id > %s " if after_id is not None else "")
                + "AND "
                + predicate
                # The primary key provides an ordered walk that can stop at LIMIT.
                # Ordering by captured_at sorts every cold row before the limit,
                # spilling a multi-million-row sort to disk on the live database.
                + " ORDER BY m.market_observation_id LIMIT %s",
                (cutoff, after_id, limit) if after_id is not None else (cutoff, limit),
            )
            return _row_dicts(cursor)

    def delete_archived_market_observations(self, ids: tuple[str, ...]) -> int:
        if not ids:
            return 0
        predicate = self._market_unreferenced_sql("m")
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('quantbet.archive_maintenance', 'on', true)"
            )
            cursor.execute(
                "DELETE FROM quantlab_market_observations m "
                "WHERE m.market_observation_id = ANY(%s) AND "
                + predicate,
                (list(ids),),
            )
            return int(cursor.rowcount)

    def watermark(self, dataset: str) -> dict[str, Any] | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT dataset, recorded_at, record_id, updated_at "
                "FROM cold_archive_watermarks WHERE dataset = %s",
                (dataset,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            columns = tuple(item.name for item in cursor.description)
            return dict(zip(columns, row, strict=True))

    def advance_watermark(
        self,
        dataset: str,
        *,
        recorded_at: datetime,
        record_id: str,
    ) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO cold_archive_watermarks "
                "(dataset, recorded_at, record_id, updated_at) "
                "VALUES (%s, %s, %s, CURRENT_TIMESTAMP) "
                "ON CONFLICT (dataset) DO UPDATE SET "
                "recorded_at = EXCLUDED.recorded_at, "
                "record_id = EXCLUDED.record_id, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE (EXCLUDED.recorded_at, EXCLUDED.record_id) > "
                "(cold_archive_watermarks.recorded_at, cold_archive_watermarks.record_id)",
                (dataset, recorded_at, record_id),
            )

    def settlement_export_rows(
        self,
        dataset: str,
        *,
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        production_sql = (
            "SELECT e.settlement_event_id, e.pick_id, e.fixture_id, e.event_kind, "
            "e.prior_event_id, e.result_observation_id, e.outcome, "
            "e.settlement_rule_version, e.rounding_version, e.entry_snapshot_id, "
            "e.entry_odd_decimal, e.stake_minor, e.gross_return_minor, "
            "e.realized_pnl_minor, e.ledger_delta_minor, e.bankroll_account_id, "
            "e.currency, e.candidate_first_seen_at, e.confirmed_at, "
            "e.confirmation_count, e.request_id, e.reason, e.actor, e.occurred_at, "
            "r.market, r.selection, r.registered_at, r.config_fingerprint "
            "FROM pick_settlement_events e "
            "JOIN registered_picks r ON r.pick_id = e.pick_id"
        )
        goallab_sql = (
            "SELECT s.goal_pick_settlement_id, s.goal_pick_id, s.fixture_id, "
            "s.result_observation_id, s.result_classification, "
            "s.regulation_home_goals, s.regulation_away_goals, s.outcome, "
            "s.pnl_minor, s.settled_at, s.settlement_rule_version, s.result_detail, "
            "p.market_key, p.selection, p.line, p.bookmaker_id, p.bookmaker_name, "
            "p.odds, p.model_name, p.model_version, p.model_probability, "
            "p.market_probability, p.edge, p.expected_value, p.decision_at "
            "FROM quantlab_goal_pick_settlements s "
            "JOIN quantlab_goal_picks p ON p.goal_pick_id = s.goal_pick_id"
        )
        cornerlab_sql = (
            "SELECT s.corner_settlement_event_id, s.shadow_bet_id, s.fixture_id, "
            "s.event_kind, s.prior_event_id, s.result_observation_id, "
            "s.statistics_observation_id, s.result_classification, s.outcome, "
            "s.pnl_minor, s.occurred_at, s.settlement_rule_version, s.result_detail, "
            "p.market_key, p.selection, p.line, p.bookmaker_id, p.bookmaker_name, "
            "p.odds, p.model_name, p.model_version, p.model_probability, "
            "p.market_probability, p.edge, p.expected_value, p.decision_at "
            "FROM quantlab_corner_settlement_events s "
            "JOIN quantlab_shadow_bets p ON p.shadow_bet_id = s.shadow_bet_id"
        )
        cardlab_sql = (
            "SELECT s.card_settlement_event_id, s.shadow_bet_id, s.fixture_id, "
            "s.fixture_observation_id, s.card_event_observation_id, s.outcome, "
            "s.pnl_minor, s.occurred_at, s.settlement_rule_version, s.result_detail, "
            "p.market_key, p.selection, p.line, p.bookmaker_id, p.bookmaker_name, "
            "p.odds, p.model_name, p.model_version, p.model_probability, "
            "p.market_probability, p.edge, p.expected_value, p.decision_at "
            "FROM quantlab_card_settlement_events s "
            "JOIN quantlab_shadow_bets p ON p.shadow_bet_id = s.shadow_bet_id"
        )
        queries = {
            "production/settlements": (
                "e.occurred_at",
                "e.settlement_event_id",
                production_sql,
            ),
            "quantlab/goallab-settlements": (
                "s.settled_at",
                "s.goal_pick_settlement_id",
                goallab_sql,
            ),
            "quantlab/cornerlab-settlements": (
                "s.occurred_at",
                "s.corner_settlement_event_id",
                cornerlab_sql,
            ),
            "quantlab/cardlab-settlements": (
                "s.occurred_at",
                "s.card_settlement_event_id",
                cardlab_sql,
            ),
        }
        if dataset not in queries:
            raise ValueError(f"unsupported settlement archive dataset: {dataset}")

        time_expr, id_expr, base = queries[dataset]
        mark = self.watermark(dataset)
        params: list[Any] = []
        where = ""
        if mark is not None:
            where = f" WHERE ({time_expr}, {id_expr}) > (%s, %s)"
            params.extend([mark["recorded_at"], mark["record_id"]])
        params.append(limit)

        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                base + where + f" ORDER BY {time_expr}, {id_expr} LIMIT %s",
                tuple(params),
            )
            return _row_dicts(cursor)



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

    def unique_rows(
        self,
        dataset: str,
        *,
        key_field: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Read archived rows while de-duplicating retry/race overlap by primary key."""
        unique: dict[str, dict[str, Any]] = {}
        for row in self.iter_rows(dataset, start=start, end=end):
            key = row.get(key_field)
            if key is None:
                raise KeyError(f"archive row is missing {key_field!r}")
            unique[str(key)] = row
        return tuple(unique.values())
