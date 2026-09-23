from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from h2h.workers.daily_bulletin import DailyBulletinWorker


class Bulletin:
    def __init__(self):
        self.calls = []

    def generate(self, day, *, as_of, horizon):
        self.calls.append((day, as_of, horizon))
        return SimpleNamespace(
            bulletin_id="daily-bulletin-v1:" + "a" * 64,
            bulletin_version="DAILY_BULLETIN_V1",
            local_date=day,
            timezone="Europe/Belgrade",
            generated_at=as_of,
            as_of=as_of,
            horizon_seconds=int(horizon.total_seconds()),
            pick_ids=("pick-1",),
            created=True,
        )


def worker_at(local_hour: int, local_minute: int, bulletin: Bulletin):
    local = datetime(
        2026,
        9,
        24,
        local_hour,
        local_minute,
        tzinfo=ZoneInfo("Europe/Belgrade"),
    )
    return DailyBulletinWorker(
        bulletin,
        horizon=timedelta(hours=72),
        clock=lambda: local.astimezone(UTC),
    )


def test_target_window_starts_at_0010_belgrade_and_uses_local_date() -> None:
    bulletin = Bulletin()
    early = worker_at(0, 9, bulletin).run_once()
    due = worker_at(0, 10, bulletin).run_once()

    assert early.due is False
    assert due.due is True
    assert bulletin.calls[0][0] == date(2026, 9, 24)
    assert bulletin.calls[0][2] == timedelta(hours=72)


def test_restart_catchup_is_bounded_and_repository_identity_remains_daily() -> None:
    bulletin = Bulletin()
    caught_up = worker_at(5, 59, bulletin).run_once()
    too_late = worker_at(6, 0, bulletin).run_once()

    assert caught_up.due is True
    assert too_late.due is False
    assert caught_up.local_date == "2026-09-24"
