"""Operational entrypoint for archive audits and verification."""

from __future__ import annotations

import json
import os

from h2h.archive.object_store import S3ObjectStore
from h2h.archive.repository import ColdArchiveCatalog, ColdArchiveReader


def main() -> None:
    mode = os.getenv("QUANTBET_ARCHIVE_MODE", "audit").strip().lower()
    catalog = ColdArchiveCatalog()

    if mode == "audit":
        print(
            json.dumps(
                {"archive_mode": "audit", "tables": catalog.table_sizes(limit=40)},
                default=str,
                separators=(",", ":"),
            )
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
        print(
            json.dumps(
                {
                    "archive_mode": "verify",
                    "dataset": dataset,
                    "batches": len(batches),
                    "manifest_rows": sum(int(item["row_count"]) for item in batches),
                    "read_back_rows": row_count,
                },
                separators=(",", ":"),
            )
        )
        return

    raise ValueError(f"unsupported QUANTBET_ARCHIVE_MODE={mode!r}")


if __name__ == "__main__":
    main()
