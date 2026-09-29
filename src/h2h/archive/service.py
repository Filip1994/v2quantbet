"""Verified immutable archive writer."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Iterable

from h2h.archive.object_store import S3ObjectStore
from h2h.archive.repository import ColdArchiveCatalog


class ColdArchiveWriter:
    def __init__(self, catalog: ColdArchiveCatalog, store: S3ObjectStore) -> None:
        self.catalog = catalog
        self.store = store

    @staticmethod
    def _canonical_rows(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in rows)

    def archive_rows(
        self,
        dataset: str,
        rows: Iterable[dict[str, Any]],
        *,
        recorded_at_field: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        materialized = self._canonical_rows(rows)
        if not materialized:
            raise ValueError("cannot archive an empty batch")

        raw = b"".join(
            json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()
            + b"\n"
            for row in materialized
        )
        payload = gzip.compress(raw, compresslevel=6, mtime=0)
        digest = hashlib.sha256(payload).hexdigest()
        safe_dataset = dataset.strip().replace("..", "_").strip("/")
        if not safe_dataset:
            raise ValueError("dataset must not be empty")
        now = datetime.now(UTC)
        object_key = (
            f"quantbet-cold/{safe_dataset}/{now:%Y/%m/%d}/{digest}.jsonl.gz"
        )

        uploaded_digest = self.store.put_bytes(
            object_key,
            payload,
            content_type="application/x-ndjson",
            content_encoding="gzip",
        )
        if uploaded_digest != digest:
            raise RuntimeError("archive upload digest mismatch")
        downloaded = self.store.get_bytes(object_key)
        verified_digest = hashlib.sha256(downloaded).hexdigest()
        if verified_digest != digest:
            raise RuntimeError("archive read-back verification failed")

        recorded: list[datetime] = []
        if recorded_at_field:
            for row in materialized:
                value = row.get(recorded_at_field)
                if isinstance(value, datetime):
                    recorded.append(value)
                elif isinstance(value, str):
                    try:
                        recorded.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
                    except ValueError:
                        pass

        batch_id = self.catalog.register_verified_batch(
            dataset=safe_dataset,
            object_key=object_key,
            row_count=len(materialized),
            compressed_bytes=len(payload),
            content_sha256=digest,
            verified_at=now,
            min_recorded_at=min(recorded) if recorded else None,
            max_recorded_at=max(recorded) if recorded else None,
            metadata=metadata,
        )
        return {
            "archive_batch_id": batch_id,
            "dataset": safe_dataset,
            "object_key": object_key,
            "row_count": len(materialized),
            "compressed_bytes": len(payload),
            "content_sha256": digest,
        }
