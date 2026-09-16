"""Deterministic Daily Bulletin over actual registered picks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from h2h.domain.pick_monitoring import PickOddsLifecycle


@dataclass(frozen=True, slots=True)
class BulletinEntry:
    pick_id: str
    decision_id: str
    evaluation_id: str
    fixture_id: str
    home_team: str
    away_team: str
    competition_name: str
    current_fixture_observation_id: str
    current_kickoff_at: datetime
    registration_fixture_observation_id: str
    registration_kickoff_at: datetime
    market: str
    selection: str
    bookmaker_id: int
    bookmaker_key: str
    source: str
    model_probability: float
    raw_implied_probability: float
    devig_probability: float
    edge: float
    expected_value: float
    stake_minor: int
    currency: str
    model_version_id: str
    policy_fingerprint: str
    registered_at: datetime
    odds: PickOddsLifecycle
    result_status: str | None = None
    result_observation_id: str | None = None
    settlement_outcome: str | None = None
    gross_return_minor: int | None = None
    realized_pnl_minor: int | None = None
    realized_clv_status: str = "PENDING_SETTLEMENT"
    realized_clv_ppm: int | None = None


class DailyBulletinReadRepository(Protocol):
    def entries_registered_between(
        self, *, start_at: datetime, end_at: datetime, as_of: datetime
    ) -> tuple[BulletinEntry, ...]: ...


class DailyBulletin:
    """Read registered picks whose registration belongs to one local calendar day."""

    def __init__(self, repository: DailyBulletinReadRepository, timezone: ZoneInfo) -> None:
        if not isinstance(timezone, ZoneInfo):
            raise TypeError("timezone must be a ZoneInfo")
        self._repository = repository
        self._timezone = timezone

    @property
    def timezone(self) -> ZoneInfo:
        return self._timezone

    def execute(self, day: date, *, as_of: datetime) -> tuple[BulletinEntry, ...]:
        if not isinstance(day, date) or isinstance(day, datetime):
            raise TypeError("day must be a date")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        local_start = datetime.combine(day, time.min, tzinfo=self._timezone)
        local_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=self._timezone)
        return self._repository.entries_registered_between(
            start_at=local_start.astimezone(UTC),
            end_at=local_end.astimezone(UTC),
            as_of=as_of.astimezone(UTC),
        )
