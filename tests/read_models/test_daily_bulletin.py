from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from h2h.read_models.daily_bulletin import DailyBulletin


class Repository:
    def __init__(self):
        self.call = None

    def entries_registered_between(self, *, start_at, end_at, as_of):
        self.call = (start_at, end_at, as_of)
        return ()


def test_belgrade_daily_boundary_uses_half_open_utc_interval() -> None:
    repository = Repository()
    bulletin = DailyBulletin(repository, ZoneInfo("Europe/Belgrade"))
    bulletin.execute(date(2026, 9, 16), as_of=datetime(2026, 9, 16, 12, tzinfo=UTC))
    assert repository.call[:2] == (
        datetime(2026, 9, 15, 22, tzinfo=UTC),
        datetime(2026, 9, 16, 22, tzinfo=UTC),
    )


def test_dst_days_have_correct_non_twenty_four_hour_utc_span() -> None:
    repository = Repository()
    bulletin = DailyBulletin(repository, ZoneInfo("Europe/Belgrade"))
    bulletin.execute(date(2026, 3, 29), as_of=datetime(2026, 3, 29, 12, tzinfo=UTC))
    start, end, _ = repository.call
    assert (end - start).total_seconds() == 23 * 3600
    bulletin.execute(date(2026, 10, 25), as_of=datetime(2026, 10, 25, 12, tzinfo=UTC))
    start, end, _ = repository.call
    assert (end - start).total_seconds() == 25 * 3600
