from datetime import datetime, timezone

from h2h.workers.quote_refresh_scheduler import QuoteRefreshScheduler

UTC = timezone.utc


def test_register_sets_next_refresh_from_current_cadence() -> None:
    scheduler = QuoteRefreshScheduler()
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    kickoff = datetime(2026, 9, 17, 12, tzinfo=UTC)

    state = scheduler.register(fixture_id=42, kickoff_at=kickoff, now=now)

    assert state is not None
    assert state.next_refresh_at == datetime(2026, 9, 16, 0, tzinfo=UTC)
    assert state.closing_capture_required is False


def test_due_fixture_ids_returns_only_due_fixtures() -> None:
    scheduler = QuoteRefreshScheduler()
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    scheduler.register(
        fixture_id=7,
        kickoff_at=datetime(2026, 9, 16, 12, tzinfo=UTC),
        now=now,
    )
    scheduler.register(
        fixture_id=42,
        kickoff_at=datetime(2026, 9, 18, 12, tzinfo=UTC),
        now=now,
    )

    assert scheduler.due_fixture_ids(
        now=datetime(2026, 9, 16, 11, 59, tzinfo=UTC)
    ) == (7,)


def test_mark_refreshed_tightens_cadence_as_kickoff_approaches() -> None:
    scheduler = QuoteRefreshScheduler()
    kickoff = datetime(2026, 9, 16, 12, tzinfo=UTC)
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    scheduler.register(fixture_id=42, kickoff_at=kickoff, now=now)

    state = scheduler.mark_refreshed(
        fixture_id=42,
        now=datetime(2026, 9, 16, 6, tzinfo=UTC),
    )

    assert state is not None
    assert state.next_refresh_at == datetime(2026, 9, 16, 8, tzinfo=UTC)


def test_mark_refreshed_marks_final_window_for_closing_capture() -> None:
    scheduler = QuoteRefreshScheduler()
    kickoff = datetime(2026, 9, 15, 13, tzinfo=UTC)
    scheduler.register(
        fixture_id=42,
        kickoff_at=kickoff,
        now=datetime(2026, 9, 15, 12, tzinfo=UTC),
    )

    state = scheduler.mark_refreshed(
        fixture_id=42,
        now=datetime(2026, 9, 15, 12, 50, tzinfo=UTC),
    )

    assert state is not None
    assert state.closing_capture_required is True


def test_register_removes_out_of_window_or_started_fixture() -> None:
    scheduler = QuoteRefreshScheduler()
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    scheduler.register(
        fixture_id=42,
        kickoff_at=datetime(2026, 9, 16, 12, tzinfo=UTC),
        now=now,
    )

    assert scheduler.register(
        fixture_id=42,
        kickoff_at=datetime(2026, 9, 18, 13, tzinfo=UTC),
        now=now,
    ) is None
    assert scheduler.snapshot() == ()


def test_remove_and_snapshot_are_deterministic() -> None:
    scheduler = QuoteRefreshScheduler()
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    kickoff = datetime(2026, 9, 16, 12, tzinfo=UTC)
    scheduler.register(fixture_id=42, kickoff_at=kickoff, now=now)
    scheduler.register(fixture_id=7, kickoff_at=kickoff, now=now)

    assert tuple(item.fixture_id for item in scheduler.snapshot()) == (7, 42)

    scheduler.remove(fixture_id=7)
    assert tuple(item.fixture_id for item in scheduler.snapshot()) == (42,)
