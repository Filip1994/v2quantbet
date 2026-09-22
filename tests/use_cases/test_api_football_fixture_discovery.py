from datetime import UTC, datetime
from unittest.mock import Mock

from h2h.use_cases.api_football_fixture_discovery import ApiFootballFixtureDiscovery
from h2h.use_cases.scoped_fixture_discovery import ScopedFixtureDiscovery


def _payload(
    fixture_id: int,
    league_id: int,
    name: str,
    country: str,
    competition_type: str = "League",
) -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": "2026-09-18T12:00:00+00:00",
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


def test_date_window_discovery_does_not_send_a_league_allowlist() -> None:
    client = Mock()
    client.fetch_fixtures.return_value = {"errors": [], "response": []}
    start = datetime(2026, 9, 17, tzinfo=UTC)
    end = datetime(2026, 9, 20, tzinfo=UTC)

    result = ApiFootballFixtureDiscovery(client).discover(start, end)

    assert result == ()
    client.fetch_fixtures.assert_called_once_with(
        start_at=start,
        end_at=end,
    )


def test_phase_i_policy_is_authoritative_for_multi_league_provider_payload() -> None:
    client = Mock()
    client.fetch_fixtures.return_value = {
        "errors": [],
        "response": [
            _payload(1, 39, "Premier League", "England"),
            _payload(2, 140, "La Liga", "Spain"),
            _payload(3, 135, "Serie A", "Italy"),
            _payload(4, 98, "J1 League", "Japan"),
            _payload(5, 1001, "Primera Division U19", "Spain"),
            _payload(6, 1002, "Copa del Rey", "Spain", "Cup"),
            _payload(7, 1003, "Premier Soccer League", "South Africa"),
            _payload(8, 41, "League Two", "England"),
            _payload(9, 1004, "Regionalliga West", "Germany"),
        ],
    }
    start = datetime(2026, 9, 17, tzinfo=UTC)
    end = datetime(2026, 9, 20, tzinfo=UTC)

    fixtures = ScopedFixtureDiscovery(ApiFootballFixtureDiscovery(client)).discover(start, end)

    assert [fixture.competition_name for fixture in fixtures] == [
        "Premier League",
        "La Liga",
        "Serie A",
        "J1 League",
    ]
    client.fetch_fixtures.assert_called_once_with(start_at=start, end_at=end)
