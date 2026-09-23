from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from h2h.read_models.daily_bulletin import DailyBulletin


class Repository:
    def __init__(self):
        self.call = None

    def actionable_entries(self, *, start_at, end_at, as_of):
        self.call = (start_at, end_at, as_of)
        return ()


def test_bulletin_projects_rolling_72_hours_not_local_registration_day() -> None:
    repository = Repository()
    bulletin = DailyBulletin(repository, ZoneInfo("Europe/Belgrade"))
    as_of = datetime(2026, 9, 16, 12, tzinfo=UTC)
    bulletin.execute(date(2026, 9, 16), as_of=as_of)
    assert repository.call[:2] == (
        as_of,
        as_of + timedelta(hours=72),
    )


def test_calendar_date_does_not_restrict_actionable_horizon() -> None:
    repository = Repository()
    bulletin = DailyBulletin(repository, ZoneInfo("Europe/Belgrade"))
    as_of = datetime(2026, 3, 29, 12, tzinfo=UTC)
    bulletin.execute(date(2026, 3, 29), as_of=as_of, horizon=timedelta(hours=48))
    start, end, _ = repository.call
    assert start == as_of
    assert end - start == timedelta(hours=48)
