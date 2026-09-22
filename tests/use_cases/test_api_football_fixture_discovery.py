from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock, call

import pytest

from h2h.use_cases.api_football_fixture_discovery import (
    ApiFootballFixtureDiscovery,
    DateShardDiscoveryError,
)
from h2h.use_cases.scoped_fixture_discovery import ScopedFixtureDiscovery


def _payload(
    fixture_id: int,
    league_id: int,
    name: str,
    country: str,
    *,
    kickoff: str = "2026-09-18T12:00:00+00:00",
    competition_type: str = "League",
) -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff,
            "status": {"short": "NS"},
        },
        "league": {
            "id": league_id,
            "name": name,
            "country": country,
            "type": competition_type,
            "season": 2026,
        },
        "teams": {
            "home": {"id": fixture_id * 2, "name": f"Home {fixture_id}"},
            "away": {"id": fixture_id * 2 + 1, "name": f"Away {fixture_id}"},
        },
    }


def _response(*fixtures: dict[str, object]) -> dict[str, object]:
    return {"errors": [], "response": list(fixtures)}


def test_multi_day_window_fetches_global_date_shards_without_scope() -> None:
    client = Mock()
    client.fetch_fixtures_for_date.return_value = _response()
    start = datetime(2026, 9, 17, 10, tzinfo=UTC)
    end = datetime(2026, 9, 19, 9, tzinfo=UTC)

    discovery = ApiFootballFixtureDiscovery(client, clock=lambda: start)

    assert discovery.discover(start, end) == ()
    assert discovery.has_pending is True
    assert discovery.discover(start, end) == ()
    assert discovery.has_pending is False

    assert client.fetch_fixtures_for_date.call_args_list == [
        call(fixture_date=date(2026, 9, 17)),
        call(fixture_date=date(2026, 9, 18)),
        call(fixture_date=date(2026, 9, 19)),
    ]
    assert all(
        set(request.kwargs) == {"fixture_date"}
        for request in client.fetch_fixtures_for_date.call_args_list
    )


def test_phase_i_policy_is_authoritative_for_multi_league_provider_payload() -> None:
    client = Mock()
    client.fetch_fixtures_for_date.return_value = _response(
        _payload(1, 39, "Premier League", "England"),
        _payload(2, 140, "La Liga", "Spain"),
        _payload(3, 135, "Serie A", "Italy"),
        _payload(4, 98, "J1 League", "Japan"),
        _payload(10, 78, "Bundesliga", "Germany"),
        _payload(11, 253, "Major League Soccer", "USA"),
        _payload(5, 1001, "Primera Division U19", "Spain"),
        _payload(6, 1002, "EFL Trophy", "England"),
        _payload(7, 1003, "Premier Soccer League", "South Africa"),
        _payload(8, 41, "League Two", "England"),
        _payload(9, 1004, "Regionalliga West", "Germany"),
        _payload(12, 1005, "KNVB Beker", "Netherlands"),
        _payload(13, 1006, "Copa Chile", "Chile"),
        _payload(14, 1007, "Non League Premier - Isthmian", "England"),
        _payload(15, 1008, "Oberliga - Bremen", "Germany"),
    )
    start = datetime(2026, 9, 18, tzinfo=UTC)
    end = datetime(2026, 9, 18, 23, 59, tzinfo=UTC)

    fixtures = ScopedFixtureDiscovery(
        ApiFootballFixtureDiscovery(client, clock=lambda: start)
    ).discover(start, end)

    assert {fixture.competition_name for fixture in fixtures} == {
        "Premier League",
        "La Liga",
        "Serie A",
        "J1 League",
        "Bundesliga",
        "Major League Soccer",
    }


def test_date_shards_are_filtered_to_exact_timestamp_window() -> None:
    client = Mock()
    client.fetch_fixtures_for_date.return_value = _response(
        _payload(1, 39, "Premier League", "England", kickoff="2026-09-18T09:59:59Z"),
        _payload(2, 39, "Premier League", "England", kickoff="2026-09-18T10:00:00Z"),
        _payload(3, 39, "Premier League", "England", kickoff="2026-09-18T11:00:00Z"),
        _payload(4, 39, "Premier League", "England", kickoff="2026-09-18T11:00:01Z"),
    )
    start = datetime(2026, 9, 18, 10, tzinfo=UTC)
    end = datetime(2026, 9, 18, 11, tzinfo=UTC)

    fixtures = ApiFootballFixtureDiscovery(client, clock=lambda: start).discover(start, end)

    assert [fixture.fixture_id for fixture in fixtures] == [
        "api-football:2",
        "api-football:3",
    ]


def test_duplicate_fixture_ids_across_shards_are_deduplicated() -> None:
    duplicate = _payload(
        42,
        140,
        "La Liga",
        "Spain",
        kickoff="2026-09-19T00:00:00Z",
    )
    client = Mock()
    client.fetch_fixtures_for_date.side_effect = [_response(duplicate), _response(duplicate)]
    start = datetime(2026, 9, 18, 23, tzinfo=UTC)
    end = datetime(2026, 9, 19, 1, tzinfo=UTC)

    fixtures = ApiFootballFixtureDiscovery(client, clock=lambda: start).discover(start, end)

    assert [fixture.fixture_id for fixture in fixtures] == ["api-football:42"]


def test_conflicting_duplicate_fixture_ids_across_shards_fail() -> None:
    first = _payload(42, 140, "La Liga", "Spain", kickoff="2026-09-19T00:00:00Z")
    conflicting = _payload(
        42,
        135,
        "Serie A",
        "Italy",
        kickoff="2026-09-19T00:00:00Z",
    )
    client = Mock()
    client.fetch_fixtures_for_date.side_effect = [_response(first), _response(conflicting)]
    start = datetime(2026, 9, 18, 23, tzinfo=UTC)
    end = datetime(2026, 9, 19, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="conflicting duplicate fixture: api-football:42"):
        ApiFootballFixtureDiscovery(client, clock=lambda: start).discover(start, end)


def test_second_cycle_fifteen_minutes_later_does_not_refetch_far_date() -> None:
    now = [datetime(2026, 9, 1, tzinfo=UTC)]
    client = Mock()
    client.fetch_fixtures_for_date.return_value = _response()
    discovery = ApiFootballFixtureDiscovery(client, clock=lambda: now[0])
    start = datetime(2026, 9, 10, tzinfo=UTC)
    end = datetime(2026, 9, 10, 23, 59, tzinfo=UTC)

    discovery.discover(start, end)
    now[0] += timedelta(minutes=15)

    assert discovery.discover(start, end) == ()
    assert client.fetch_fixtures_for_date.call_count == 1


def test_cached_shard_is_refiltered_when_exact_window_rolls() -> None:
    now = [datetime(2026, 9, 1, 10, tzinfo=UTC)]
    client = Mock()
    client.fetch_fixtures_for_date.return_value = _response(
        _payload(
            42,
            140,
            "La Liga",
            "Spain",
            kickoff="2026-09-10T10:10:00Z",
        )
    )
    discovery = ApiFootballFixtureDiscovery(client, clock=lambda: now[0])

    initial_end = datetime(2026, 9, 10, 10, tzinfo=UTC)
    while True:
        assert discovery.discover(now[0], initial_end) == ()
        if not discovery.has_pending:
            break
    now[0] += timedelta(minutes=15)
    fixtures = discovery.discover(now[0], datetime(2026, 9, 10, 10, 15, tzinfo=UTC))

    assert [fixture.fixture_id for fixture in fixtures] == ["api-football:42"]
    assert client.fetch_fixtures_for_date.call_count == 10


def test_far_future_date_becomes_refreshable_after_twenty_four_hours() -> None:
    now = [datetime(2026, 9, 1, tzinfo=UTC)]
    client = Mock()
    client.fetch_fixtures_for_date.return_value = _response()
    discovery = ApiFootballFixtureDiscovery(client, clock=lambda: now[0])
    start = datetime(2026, 9, 10, tzinfo=UTC)
    end = datetime(2026, 9, 10, 23, 59, tzinfo=UTC)

    discovery.discover(start, end)
    now[0] += timedelta(hours=24)
    discovery.discover(start, end)

    assert client.fetch_fixtures_for_date.call_count == 2


def test_date_inside_next_seventy_two_hours_uses_six_hour_refresh() -> None:
    now = [datetime(2026, 9, 1, tzinfo=UTC)]
    client = Mock()
    client.fetch_fixtures_for_date.return_value = _response()
    discovery = ApiFootballFixtureDiscovery(client, clock=lambda: now[0])
    start = datetime(2026, 9, 3, tzinfo=UTC)
    end = datetime(2026, 9, 3, 23, 59, tzinfo=UTC)

    discovery.discover(start, end)
    now[0] += timedelta(hours=5, minutes=59)
    discovery.discover(start, end)
    now[0] += timedelta(minutes=1)
    discovery.discover(start, end)

    assert client.fetch_fixtures_for_date.call_count == 2


def test_cold_start_populates_complete_twenty_one_day_horizon() -> None:
    client = Mock()
    client.fetch_fixtures_for_date.return_value = _response()
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 21, 23, 59, tzinfo=UTC)

    discovery = ApiFootballFixtureDiscovery(client, clock=lambda: start)
    while True:
        discovery.discover(start, end)
        if not discovery.has_pending:
            break

    assert client.fetch_fixtures_for_date.call_count == 21


def test_failed_shard_is_explicit_and_partial_horizon_is_not_returned() -> None:
    now = [datetime(2026, 9, 1, tzinfo=UTC)]
    first_fixture = _payload(
        1,
        39,
        "Premier League",
        "England",
        kickoff="2026-09-01T12:00:00Z",
    )
    second_fixture = _payload(
        2,
        140,
        "La Liga",
        "Spain",
        kickoff="2026-09-02T12:00:00Z",
    )
    client = Mock()
    client.fetch_fixtures_for_date.side_effect = [
        _response(first_fixture),
        RuntimeError("provider unavailable"),
        _response(second_fixture),
    ]
    discovery = ApiFootballFixtureDiscovery(client, clock=lambda: now[0])
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 2, 23, 59, tzinfo=UTC)

    with pytest.raises(DateShardDiscoveryError, match="2026-09-02 failed"):
        discovery.discover(start, end)

    now[0] += timedelta(minutes=15)
    with pytest.raises(DateShardDiscoveryError, match="retry deferred"):
        discovery.discover(start, end)
    assert client.fetch_fixtures_for_date.call_count == 2

    now[0] += timedelta(minutes=45)
    fixtures = discovery.discover(start, end)

    assert [fixture.fixture_id for fixture in fixtures] == [
        "api-football:1",
        "api-football:2",
    ]
    assert client.fetch_fixtures_for_date.call_args_list == [
        call(fixture_date=date(2026, 9, 1)),
        call(fixture_date=date(2026, 9, 2)),
        call(fixture_date=date(2026, 9, 2)),
    ]
