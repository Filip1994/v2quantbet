"""Scheduled Production funnel intake."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from collections.abc import Callable

from h2h.persistence.postgres_production_funnel import (
    PostgreSQLProductionFunnelRepository,
    ProductionFunnelSyncResult,
    active_bucket_ids,
)


LOGGER = logging.getLogger("quantbet.production_funnel")


class ProductionFunnelWorker:
    def __init__(
        self,
        repository: PostgreSQLProductionFunnelRepository,
        *,
        max_open_exposure_minor: int,
        currency: str,
        fallback_stake_minor: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if max_open_exposure_minor <= 0 or fallback_stake_minor <= 0:
            raise ValueError("Production funnel stake and exposure limits must be positive")
        self._repository = repository
        self._max_open_exposure_minor = max_open_exposure_minor
        self._currency = currency
        self._fallback_stake_minor = fallback_stake_minor
        self._clock = clock

    def run_once(self) -> ProductionFunnelSyncResult:
        bucket_ids = active_bucket_ids()
        result = self._repository.sync(
            now=self._clock(),
            max_open_exposure_minor=self._max_open_exposure_minor,
            currency=self._currency,
            fallback_stake_minor=self._fallback_stake_minor,
            bucket_ids=bucket_ids,
        )
        LOGGER.info(
            "production funnel intake outcomes",
            extra={
                "worker": "production_intake",
                "candidates_seen": result.candidates_seen,
                "matched_candidates": result.matched_candidates,
                "cloned_picks": result.cloned_picks,
                "duplicate_candidates": result.duplicate_candidates,
                "exposure_blocked": result.exposure_blocked,
                "open_exposure_minor": result.open_exposure_minor,
                "intake_contract_version": result.intake_contract_version,
                "active_bucket_ids": bucket_ids,
            },
        )
        return result
