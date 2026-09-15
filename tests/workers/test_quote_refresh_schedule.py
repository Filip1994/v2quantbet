from datetime import datetime, timedelta, timezone

import pytest

from h2h.workers.quote_refresh_schedule import quote_refresh_decision


UTC = timezone.utc
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(hours=72), timedelta(hours=24)),
        (timedelta(hours=48), timedelta(hours=12)),
        (timedelta(hours=24), timedelta(hours=6)),
        (timedelta(hours=6), timedelta(hours=2)),
        (timedelta(hours=2), timedelta(minutes=30)),
        (timedelta(minutes=16), timedelta(minutes=30)),
    ],
)
def test_boundaries_use_conservative_cadence(delta, expected):
    decision = quote_refresh_decision(now=NOW, kickoff_at=NOW + delta)

    assert decision.eligible is True
    assert decision.interval == expected
    assert decision.closing_capture is False


def test_final_fifteen_minutes_marks_closing_capture():
    decision = quote_refresh_decision(
        now=NOW,
        kickoff_at=NOW + timedelta(minutes=15),
    )

    assert decision.eligible is True
    assert decision.interval == timedelta(minutes=30)
    assert decision.closing_capture is True


@pytest.mark.parametrize(
    "delta",
    [timedelta(seconds=0), timedelta(seconds=-1)],
)
def test_started_fixture_is_not_eligible(delta):
    decision = quote_refresh_decision(now=NOW, kickoff_at=NOW + delta)

    assert decision.eligible is False
    assert decision.interval is None


def test_fixture_beyond_lookahead_is_not_eligible():
    decision = quote_refresh_decision(
        now=NOW,
        kickoff_at=NOW + timedelta(hours=72, seconds=1),
    )

    assert decision.eligible is False
    assert decision.interval is None


@pytest.mark.parametrize("field", ["now", "kickoff_at"])
def test_naive_datetime_is_rejected(field):
    values = {
        "now": NOW,
        "kickoff_at": NOW + timedelta(hours=1),
    }
    values[field] = values[field].replace(tzinfo=None)

    with pytest.raises(ValueError, match="timezone-aware"):
        quote_refresh_decision(**values)
