"""Production Dixon-Coles coverage and training policy contracts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from math import isfinite


class ModelCoverageStatus(StrEnum):
    ACTIVE = "ACTIVE"
    MISSING = "MISSING"
    TRAINING_REQUIRED = "TRAINING_REQUIRED"
    TRAINING_PENDING = "TRAINING_PENDING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    TRAINING_FAILED = "TRAINING_FAILED"
    STALE = "STALE"
    RETRAIN_REQUIRED = "RETRAIN_REQUIRED"


@dataclass(frozen=True, slots=True)
class ProductionTrainingPolicy:
    """Validated, fingerprinted policy for every production training decision."""

    history_window_days: int = 730
    min_matches: int = 80
    xi: float = 0.0018
    ridge: float = 0.01
    freshness_days: int = 14
    previous_seasons: int = 1
    min_team_matches: int = 3
    trainer_version: str = "production-dc-v1"

    def __post_init__(self) -> None:
        for name in (
            "history_window_days",
            "min_matches",
            "freshness_days",
            "min_team_matches",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.previous_seasons, bool)
            or not isinstance(self.previous_seasons, int)
            or self.previous_seasons < 0
        ):
            raise ValueError("previous_seasons must be a non-negative integer")
        for name in ("xi", "ridge"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not self.trainer_version.strip():
            raise ValueError("trainer_version must not be blank")

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()

    @property
    def provenance_trainer_version(self) -> str:
        return f"{self.trainer_version}:{self.fingerprint}"

    def reference_time(self, now: datetime) -> datetime:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("reference time source must be timezone-aware")
        current = now.astimezone(UTC)
        return current.replace(hour=0, minute=0, second=0, microsecond=0)

    def training_window(self, now: datetime) -> tuple[datetime, datetime]:
        end = self.reference_time(now)
        return end - timedelta(days=self.history_window_days), end

    def allowed_training_seasons(self, target_season: int) -> tuple[int, ...]:
        if isinstance(target_season, bool) or target_season <= 0:
            raise ValueError("target_season must be positive")
        return tuple(target_season - lag for lag in range(self.previous_seasons + 1))
