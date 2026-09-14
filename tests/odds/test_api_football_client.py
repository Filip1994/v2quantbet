from unittest.mock import Mock

import pytest

from h2h.odds.api_football_client import ApiFootballClient


def test_fetch_odds_uses_injected_transport() -> None:
    transport = Mock()
    transport.get_json.return_value = {"response": [{"fixture": {"id": 42}}]}

    result = ApiFootballClient(transport, "secret").fetch_odds(fixture_id=42)

    assert result == {"response": [{"fixture": {"id": 42}}]}
    transport.get_json.assert_called_once_with(
        "https://v3.football.api-sports.io/odds?fixture=42",
        headers={"x-apisports-key": "secret"},
        timeout=10.0,
    )


def test_fetch_odds_uses_fresh_fixture_cache() -> None:
    transport = Mock()
    transport.get_json.return_value = {"response": [42]}
    now = [100.0]
    client = ApiFootballClient(transport, "secret", cache_ttl_seconds=30, clock=lambda: now[0])

    assert client.fetch_odds(fixture_id=42) == {"response": [42]}
    now[0] = 120.0
    assert client.fetch_odds(fixture_id=42) == {"response": [42]}
    transport.get_json.assert_called_once()


def test_fetch_odds_refreshes_expired_fixture_cache() -> None:
    transport = Mock()
    transport.get_json.side_effect = [{"response": [1]}, {"response": [2]}]
    now = [100.0]
    client = ApiFootballClient(transport, "secret", cache_ttl_seconds=30, clock=lambda: now[0])

    assert client.fetch_odds(fixture_id=42) == {"response": [1]}
    now[0] = 130.0
    assert client.fetch_odds(fixture_id=42) == {"response": [2]}
    assert transport.get_json.call_count == 2


def test_clear_cache_forces_refresh() -> None:
    transport = Mock()
    transport.get_json.side_effect = [{"response": [1]}, {"response": [2]}]
    client = ApiFootballClient(transport, "secret", cache_ttl_seconds=30)

    client.fetch_odds(fixture_id=42)
    client.clear_cache()
    assert client.fetch_odds(fixture_id=42) == {"response": [2]}


@pytest.mark.parametrize("fixture_id", [0, -1])
def test_fixture_id_must_be_positive(fixture_id: int) -> None:
    with pytest.raises(ValueError, match="fixture_id"):
        ApiFootballClient(Mock(), "secret").fetch_odds(fixture_id=fixture_id)


def test_api_key_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="api_key"):
        ApiFootballClient(Mock(), " ").fetch_odds(fixture_id=1)


def test_cache_ttl_must_not_be_negative() -> None:
    with pytest.raises(ValueError, match="cache_ttl_seconds"):
        ApiFootballClient(Mock(), "secret", cache_ttl_seconds=-1).fetch_odds(fixture_id=1)
