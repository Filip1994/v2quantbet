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
