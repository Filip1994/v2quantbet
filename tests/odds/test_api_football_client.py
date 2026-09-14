from unittest.mock import Mock

import pytest

from h2h.odds.api_football_client import ApiFootballClient


def test_fetch_odds_uses_injected_transport() -> None:
    transport = Mock()
    transport.get_json.return_value = {"response": [{"fixture": {"id": 42}}]}

    result = ApiFootballClient(transport, "secret").fetch_odds(fixture_id=42)

    assert result == {"response": [{"fixture": {"id": 42}}]}
    transport.get_json.assert_called_once_with(
        "https://v3.football.api-sports.io/odds",
        headers={"x-apisports-key": "secret"},
        timeout=10.0,
    )


@pytest.mark.parametrize("fixture_id", [0, -1])
def test_fixture_id_must_be_positive(fixture_id: int) -> None:
    with pytest.raises(ValueError, match="fixture_id"):
        ApiFootballClient(Mock(), "secret").fetch_odds(fixture_id=fixture_id)


def test_api_key_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="api_key"):
        ApiFootballClient(Mock(), " ").fetch_odds(fixture_id=1)
