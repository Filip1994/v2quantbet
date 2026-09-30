from datetime import UTC, datetime

from h2h.api.dashboard_time import (
    COUNTDOWN_SCRIPT,
    COUNTDOWN_SCRIPT_CSP,
    kickoff_countdown,
    local_iso,
    local_time,
)


def test_belgrade_display_handles_summer_and_winter_offsets() -> None:
    assert local_time(datetime(2026, 9, 30, 12, tzinfo=UTC), "%H:%M") == "14:00"
    assert local_time(datetime(2026, 12, 30, 12, tzinfo=UTC), "%H:%M") == "13:00"
    assert local_iso("2026-12-30T12:00:00+00:00") == "2026-12-30 13:00"


def test_countdown_uses_absolute_kickoff_and_csp_allows_its_script() -> None:
    markup = kickoff_countdown(datetime(2026, 9, 30, 12, tzinfo=UTC))
    assert 'data-kickoff="2026-09-30T12:00:00+00:00"' in markup
    assert "Date.now()" in COUNTDOWN_SCRIPT
    assert "fetch(" not in COUNTDOWN_SCRIPT
    assert "sha256-" in COUNTDOWN_SCRIPT_CSP
