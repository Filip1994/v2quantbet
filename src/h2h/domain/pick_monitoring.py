"""Durable registered-pick odds lifecycle records and read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


ODDS_LIFECYCLE_V1 = "ODDS_LIFECYCLE_V1"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value


class MonitoringState(StrEnum):
    REGISTERED = "REGISTERED"
    MONITORING = "MONITORING"
    CLOSED_FOR_ODDS = "CLOSED_FOR_ODDS"


class MonitoringTransitionType(StrEnum):
    MONITORING_STARTED = "MONITORING_STARTED"
    ODDS_CLOSED = "ODDS_CLOSED"


class ClosingOutcome(StrEnum):
    CAPTURED = "CAPTURED"
    NO_VALID_QUOTE = "NO_VALID_QUOTE"
    STALE_QUOTE = "STALE_QUOTE"


class QuoteFreshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class OddsLifecyclePolicy:
    monitoring_interval_seconds: int
    current_max_age_seconds: int
    closing_max_age_seconds: int
    version: str = ODDS_LIFECYCLE_V1

    def __post_init__(self) -> None:
        for name in (
            "monitoring_interval_seconds",
            "current_max_age_seconds",
            "closing_max_age_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.version != ODDS_LIFECYCLE_V1:
            raise ValueError(f"version must be {ODDS_LIFECYCLE_V1}")


@dataclass(frozen=True, slots=True)
class MonitoringRecord:
    pick_id: str
    state: MonitoringState
    policy: OddsLifecyclePolicy
    started_at: datetime
    next_refresh_at: datetime | None
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        _text(self.pick_id, "pick_id")
        object.__setattr__(self, "started_at", _utc(self.started_at, "started_at"))
        object.__setattr__(self, "updated_at", _utc(self.updated_at, "updated_at"))
        if self.next_refresh_at is not None:
            object.__setattr__(
                self, "next_refresh_at", _utc(self.next_refresh_at, "next_refresh_at")
            )
        if self.state is MonitoringState.MONITORING and self.next_refresh_at is None:
            raise ValueError("MONITORING requires next_refresh_at")
        if self.state is MonitoringState.CLOSED_FOR_ODDS and self.next_refresh_at is not None:
            raise ValueError("CLOSED_FOR_ODDS cannot have next_refresh_at")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version <= 0:
            raise ValueError("version must be positive")


@dataclass(frozen=True, slots=True)
class ClosingFinalization:
    finalization_id: str
    pick_id: str
    fixture_id: str
    fixture_observation_id: str
    cutoff_at: datetime
    series_id: str
    source: str
    finalized_at: datetime
    outcome: ClosingOutcome
    candidate_snapshot_id: str | None
    closing_snapshot_id: str | None
    policy_version: str
    closing_max_age_seconds: int

    def __post_init__(self) -> None:
        for name in (
            "finalization_id",
            "pick_id",
            "fixture_id",
            "fixture_observation_id",
            "series_id",
            "source",
        ):
            _text(getattr(self, name), name)
        object.__setattr__(self, "cutoff_at", _utc(self.cutoff_at, "cutoff_at"))
        object.__setattr__(self, "finalized_at", _utc(self.finalized_at, "finalized_at"))
        if self.finalized_at < self.cutoff_at:
            raise ValueError("finalized_at cannot precede cutoff_at")
        if self.policy_version != ODDS_LIFECYCLE_V1:
            raise ValueError("unsupported lifecycle policy")
        if self.closing_max_age_seconds <= 0:
            raise ValueError("closing_max_age_seconds must be positive")
        if self.outcome is ClosingOutcome.CAPTURED:
            if self.candidate_snapshot_id is None or (
                self.closing_snapshot_id != self.candidate_snapshot_id
            ):
                raise ValueError("CAPTURED requires one matching candidate and closing snapshot")
        elif self.outcome is ClosingOutcome.NO_VALID_QUOTE:
            if self.candidate_snapshot_id is not None or self.closing_snapshot_id is not None:
                raise ValueError("NO_VALID_QUOTE cannot reference a snapshot")
        elif self.candidate_snapshot_id is None or self.closing_snapshot_id is not None:
            raise ValueError("STALE_QUOTE requires only a candidate snapshot")


@dataclass(frozen=True, slots=True)
class OddsCheckpoint:
    snapshot_id: str
    series_id: str
    odd: float
    observed_at: datetime
    captured_at: datetime
    source: str
    freshness: QuoteFreshness | None = None

    def __post_init__(self) -> None:
        for name in ("snapshot_id", "series_id", "source"):
            _text(getattr(self, name), name)
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "captured_at", _utc(self.captured_at, "captured_at"))
        if self.odd <= 1.0:
            raise ValueError("odd must be greater than 1")

    def is_fresh_at(self, reference_at: datetime, max_age_seconds: int) -> bool:
        reference = _utc(reference_at, "reference_at")
        maximum = timedelta(seconds=max_age_seconds)
        return (
            timedelta(0) <= reference - self.observed_at <= maximum
            and timedelta(0) <= reference - self.captured_at <= maximum
        )


@dataclass(frozen=True, slots=True)
class PickOddsLifecycle:
    pick_id: str
    state: MonitoringState
    opening: OddsCheckpoint | None
    entry: OddsCheckpoint
    current: OddsCheckpoint | None
    closing: OddsCheckpoint | None
    closing_outcome: ClosingOutcome | None
    history: tuple[OddsCheckpoint, ...]
    markers: dict[str, tuple[str, ...]]
