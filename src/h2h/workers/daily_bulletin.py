"""Once-per-local-day durable Daily Bulletin scheduling."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from h2h.read_models.daily_bulletin import DailyBulletin


LOGGER = logging.getLogger("quantbet.daily_bulletin")
BELGRADE = ZoneInfo("Europe/Belgrade")


@dataclass(frozen=True, slots=True)
class DailyBulletinCycle:
    due: bool
    bulletin_id: str | None = None
    local_date: str | None = None
    membership_count: int = 0


class DailyBulletinWorker:
    """Generate in the 00:10 target window, with bounded restart catch-up to 06:00."""

    def __init__(
        self,
        bulletin: DailyBulletin,
        *,
        horizon: timedelta,
        timezone: ZoneInfo = BELGRADE,
        target_time: time = time(0, 10),
        catch_up_until: time = time(6, 0),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if horizon <= timedelta(0):
            raise ValueError("bulletin horizon must be positive")
        if target_time >= catch_up_until:
            raise ValueError("bulletin target time must precede catch-up cutoff")
        self._bulletin = bulletin
        self._horizon = horizon
        self._timezone = timezone
        self._target_time = target_time
        self._catch_up_until = catch_up_until
        self._clock = clock
        self._last_completed_date = None

    def run_once(self) -> DailyBulletinCycle:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        current = now.astimezone(UTC)
        local = current.astimezone(self._timezone)
        if not self._target_time <= local.time().replace(tzinfo=None) < self._catch_up_until:
            return DailyBulletinCycle(False, local_date=local.date().isoformat())
        if self._last_completed_date == local.date():
            return DailyBulletinCycle(False, local_date=local.date().isoformat())
        snapshot = self._bulletin.generate(local.date(), as_of=current, horizon=self._horizon)
        self._last_completed_date = local.date()
        LOGGER.info(
            (
                "daily bulletin generated"
                if snapshot.created
                else "daily bulletin duplicate generation suppressed"
            ),
            extra={
                "worker": "daily_bulletin",
                "bulletin_id": snapshot.bulletin_id,
                "bulletin_version": snapshot.bulletin_version,
                "bulletin_local_date": snapshot.local_date.isoformat(),
                "bulletin_timezone": snapshot.timezone,
                "generated_at": snapshot.generated_at,
                "as_of": snapshot.as_of,
                "horizon_seconds": snapshot.horizon_seconds,
                "bulletin_membership_count": len(snapshot.pick_ids),
            },
        )
        return DailyBulletinCycle(
            snapshot.created,
            snapshot.bulletin_id,
            snapshot.local_date.isoformat(),
            len(snapshot.pick_ids),
        )
