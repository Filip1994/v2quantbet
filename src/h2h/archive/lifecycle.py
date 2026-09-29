"""Long-term hot/cold lifecycle for QuantBet evidence.

High-volume unreferenced market observations move to Durable Barrel after a short hot
window. Decision/pick evidence remains in PostgreSQL. Immutable settlement ledgers are
mirrored to the bucket but retained in PostgreSQL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from h2h.archive.object_store import S3ObjectStore
from h2h.archive.repository import ColdArchiveCatalog
from h2h.archive.service import ColdArchiveWriter


@dataclass(frozen=True)
class ArchiveLifecycleConfig:
    market_hot_hours: int = 72
    market_batch_size: int = 5000
    market_max_batches: int = 20
    settlement_batch_size: int = 2000

    @classmethod
    def from_environment(cls) -> "ArchiveLifecycleConfig":
        def integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
            raw = os.getenv(name, "").strip()
            value = default if not raw else int(raw)
            if value < minimum or value > maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
            return value

        return cls(
            market_hot_hours=integer(
                "QUANTBET_ARCHIVE_MARKET_HOT_HOURS", 72, minimum=24, maximum=720
            ),
            market_batch_size=integer(
                "QUANTBET_ARCHIVE_MARKET_BATCH_SIZE", 5000, minimum=100, maximum=20000
            ),
            market_max_batches=integer(
                "QUANTBET_ARCHIVE_MARKET_MAX_BATCHES", 20, minimum=1, maximum=200
            ),
            settlement_batch_size=integer(
                "QUANTBET_ARCHIVE_SETTLEMENT_BATCH_SIZE",
                2000,
                minimum=100,
                maximum=10000,
            ),
        )


class ArchiveLifecycleService:
    MARKET_DATASET = "quantlab/market-observations"
    SETTLEMENT_DATASETS = (
        "production/settlements",
        "quantlab/goallab-settlements",
        "quantlab/cornerlab-settlements",
        "quantlab/cardlab-settlements",
    )

    def __init__(
        self,
        catalog: ColdArchiveCatalog,
        store: S3ObjectStore,
        *,
        config: ArchiveLifecycleConfig | None = None,
    ) -> None:
        self.catalog = catalog
        self.writer = ColdArchiveWriter(catalog, store)
        self.config = config or ArchiveLifecycleConfig.from_environment()

    def run(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(UTC)
        return {
            "market": self.archive_cold_market_observations(now=current),
            "settlements": {
                dataset: self.mirror_settlements(dataset)
                for dataset in self.SETTLEMENT_DATASETS
            },
            "largest_tables": self.catalog.table_sizes(limit=12),
        }

    def archive_cold_market_observations(self, *, now: datetime) -> dict[str, Any]:
        cutoff = now - timedelta(hours=self.config.market_hot_hours)
        archived_rows = 0
        deleted_rows = 0
        compressed_bytes = 0
        batches = 0

        for _ in range(self.config.market_max_batches):
            rows = self.catalog.market_archive_candidates(
                cutoff=cutoff,
                limit=self.config.market_batch_size,
            )
            if not rows:
                break
            archived = self.writer.archive_rows(
                self.MARKET_DATASET,
                rows,
                recorded_at_field="captured_at",
                metadata={
                    "source_table": "quantlab_market_observations",
                    "retention_class": "high-volume-market-evidence",
                    "hot_hours": self.config.market_hot_hours,
                },
            )
            ids = tuple(str(row["market_observation_id"]) for row in rows)
            deleted = self.catalog.delete_archived_market_observations(ids)
            self.catalog.mark_deleted_from_hot(
                archived["archive_batch_id"],
                deleted_rows=deleted,
                selected_rows=len(rows),
            )
            batches += 1
            archived_rows += len(rows)
            deleted_rows += deleted
            compressed_bytes += int(archived["compressed_bytes"])

            # A newly-created FK reference can legitimately race the archive selection.
            # Such a row stays hot forever as decision evidence; continue with later rows.
            if len(rows) < self.config.market_batch_size:
                break

        return {
            "cutoff": cutoff.isoformat(),
            "hot_hours": self.config.market_hot_hours,
            "batches": batches,
            "archived_rows": archived_rows,
            "deleted_rows": deleted_rows,
            "compressed_bytes": compressed_bytes,
        }

    def mirror_settlements(self, dataset: str) -> dict[str, Any]:
        rows = self.catalog.settlement_export_rows(
            dataset,
            limit=self.config.settlement_batch_size,
        )
        if not rows:
            return {"rows": 0, "archived": False}

        time_field = {
            "production/settlements": "occurred_at",
            "quantlab/goallab-settlements": "settled_at",
            "quantlab/cornerlab-settlements": "occurred_at",
            "quantlab/cardlab-settlements": "occurred_at",
        }[dataset]
        id_field = {
            "production/settlements": "settlement_event_id",
            "quantlab/goallab-settlements": "goal_pick_settlement_id",
            "quantlab/cornerlab-settlements": "corner_settlement_event_id",
            "quantlab/cardlab-settlements": "card_settlement_event_id",
        }[dataset]
        archived = self.writer.archive_rows(
            dataset,
            rows,
            recorded_at_field=time_field,
            metadata={
                "retention_class": "permanent-ledger-mirror",
                "hot_retention": "permanent",
            },
        )
        last = rows[-1]
        self.catalog.advance_watermark(
            dataset,
            recorded_at=last[time_field],
            record_id=str(last[id_field]),
        )
        return {
            "rows": len(rows),
            "archived": True,
            "compressed_bytes": archived["compressed_bytes"],
            "watermark_at": str(last[time_field]),
            "watermark_id": str(last[id_field]),
        }
