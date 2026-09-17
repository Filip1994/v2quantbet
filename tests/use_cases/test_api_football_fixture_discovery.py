from datetime import UTC, datetime
from unittest.mock import Mock

from h2h.use_cases.api_football_fixture_discovery import ApiFootballFixtureDiscovery


def test_scoped_discovery_requests_each_exact_provider_scope() -> None:
    client = Mock()
    client.fetch_fixtures.return_value = {"errors": [], "response": []}
    start = datetime(2026, 9, 17, tzinfo=UTC)
    end = datetime(2026, 9, 20, tzinfo=UTC)

    result = ApiFootballFixtureDiscovery(client, scope_pairs=((39, 2026),)).discover(
        start, end
    )

    assert result == ()
    client.fetch_fixtures.assert_called_once_with(
        start_at=start,
        end_at=end,
        league_id=39,
        season=2026,
    )
