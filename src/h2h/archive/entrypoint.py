"""Operational entrypoint for archive audits and verification."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from h2h.archive.object_store import S3ObjectStore
from h2h.archive.repository import ColdArchiveCatalog, ColdArchiveReader
from h2h.archive.service import ColdArchiveWriter


def _print(payload: object) -> None:
    print(json.dumps(payload, default=str, separators=(",", ":")))


def main() -> None:
    mode = os.getenv("QUANTBET_ARCHIVE_MODE", "audit").strip().lower()
    catalog = ColdArchiveCatalog()

    if mode == "audit":
        _print({"archive_mode": "audit", "tables": catalog.table_sizes(limit=40)})
        return

    if mode == "throttle-audit":
        with catalog.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT category, request_count, updated_at "
                "FROM provider_request_usage WHERE request_day = CURRENT_DATE "
                "ORDER BY category"
            )
            api_usage = cursor.fetchall()

            cursor.execute(
                "SELECT status, COUNT(*) FROM model_coverage_scopes "
                "WHERE eligible GROUP BY status ORDER BY status"
            )
            model_coverage = cursor.fetchall()

            cursor.execute(
                "SELECT freshness_state, COUNT(*), "
                "COUNT(*) FILTER (WHERE next_retry_at IS NOT NULL "
                "AND next_retry_at <= CURRENT_TIMESTAMP), "
                "MIN(next_retry_at), MAX(last_attempt_at) "
                "FROM production_quote_refresh_states "
                "GROUP BY freshness_state ORDER BY freshness_state"
            )
            quote_refresh = cursor.fetchall()

            cursor.execute(
                "SELECT last_error_class, COUNT(*), MIN(next_retry_at), MAX(next_retry_at) "
                "FROM production_item_failures "
                "WHERE worker_name = 'opportunity' "
                "GROUP BY last_error_class ORDER BY COUNT(*) DESC"
            )
            opportunity_failures = cursor.fetchall()

            cursor.execute(
                "SELECT decision, reason, COUNT(*) "
                "FROM quantlab_goal_decisions "
                "WHERE decision_at >= CURRENT_TIMESTAMP - INTERVAL '6 hours' "
                "GROUP BY decision, reason ORDER BY COUNT(*) DESC, decision, reason"
            )
            goal_reasons = cursor.fetchall()

            cursor.execute(
                "SELECT COUNT(*), MAX(decision_at), "
                "COUNT(*) FILTER (WHERE decision_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours') "
                "FROM quantlab_goal_picks"
            )
            goal_picks = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*), MAX(qualified_at), "
                "COUNT(*) FILTER (WHERE qualified_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours') "
                "FROM research_signals"
            )
            research_signals = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*), MAX(registered_at), "
                "COUNT(*) FILTER (WHERE registered_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours') "
                "FROM registered_picks"
            )
            registered_picks = cursor.fetchone()

        _print(
            {
                "archive_mode": "throttle-audit",
                "api_usage": api_usage,
                "model_coverage": model_coverage,
                "quote_refresh": quote_refresh,
                "opportunity_failures": opportunity_failures,
                "goallab_reasons_6h": goal_reasons,
                "goallab_picks": goal_picks,
                "research_signals": research_signals,
                "registered_picks": registered_picks,
            }
        )
        return

    if mode == "market-stats":
        _print(
            {
                "archive_mode": "market-stats",
                "stats": catalog.market_observation_stats(),
            }
        )
        return

    if mode == "smoke":
        store = S3ObjectStore.from_environment()
        writer = ColdArchiveWriter(catalog, store)
        reader = ColdArchiveReader(catalog, store)
        now = datetime.now(UTC)
        probe = {
            "probe": "quantbet-durable-barrel-smoke-v1",
            "recorded_at": now,
        }
        archived = writer.archive_rows(
            "_smoke",
            (probe,),
            recorded_at_field="recorded_at",
            metadata={"purpose": "connectivity-check"},
        )
        restored = reader.rows("_smoke")
        matched = any(
            row.get("probe") == probe["probe"]
            and row.get("recorded_at") == str(now)
            for row in restored
        )
        if not matched:
            raise RuntimeError("Durable Barrel smoke read-back did not match")
        _print(
            {
                "archive_mode": "smoke",
                "status": "ok",
                "archive_batch_id": archived["archive_batch_id"],
                "object_key": archived["object_key"],
                "row_count": archived["row_count"],
                "compressed_bytes": archived["compressed_bytes"],
            }
        )
        return

    if mode == "verify":
        dataset = os.getenv("QUANTBET_ARCHIVE_DATASET", "").strip()
        if not dataset:
            raise ValueError("QUANTBET_ARCHIVE_DATASET is required for verify mode")
        store = S3ObjectStore.from_environment()
        reader = ColdArchiveReader(catalog, store)
        batches = catalog.list_batches(dataset)
        row_count = sum(1 for _ in reader.iter_rows(dataset))
        _print(
            {
                "archive_mode": "verify",
                "dataset": dataset,
                "batches": len(batches),
                "manifest_rows": sum(int(item["row_count"]) for item in batches),
                "read_back_rows": row_count,
            }
        )
        return

    raise ValueError(f"unsupported QUANTBET_ARCHIVE_MODE={mode!r}")


if __name__ == "__main__":
    main()
