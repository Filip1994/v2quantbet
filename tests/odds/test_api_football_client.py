from unittest.mock import Mock
from datetime import UTC, datetime, timedelta, timezone

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


@pytest.mark.parametrize("fixture_id", [0, -1, True, 42.0, "42"])
def test_fixture_id_must_be_positive_integer(fixture_id: object) -> None:
    with pytest.raises(ValueError, match="fixture_id"):
        ApiFootballClient(Mock(), "secret").fetch_odds(fixture_id=fixture_id)  # type: ignore[arg-type]


def test_api_key_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="api_key"):
        ApiFootballClient(Mock(), " ").fetch_odds(fixture_id=1)


@pytest.mark.parametrize("ttl", [-1, True, float("inf"), "30"])
def test_cache_ttl_must_be_non_negative_finite_number(ttl: object) -> None:
    with pytest.raises(ValueError, match="cache_ttl_seconds"):
        ApiFootballClient(Mock(), "secret", cache_ttl_seconds=ttl).fetch_odds(fixture_id=1)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf"), "10"])
def test_timeout_must_be_positive_finite_number(timeout: object) -> None:
    with pytest.raises(ValueError, match="timeout"):
        ApiFootballClient(Mock(), "secret", timeout=timeout).fetch_odds(fixture_id=1)  # type: ignore[arg-type]


def test_base_url_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="base_url"):
        ApiFootballClient(Mock(), "secret", base_url=" ").fetch_odds(fixture_id=1)


def test_fetch_completed_fixtures_uses_exact_ft_scope_and_utc_dates() -> None:
    transport = Mock()
    transport.get_json.return_value = {"response": []}
    client = ApiFootballClient(transport, "secret")

    result = client.fetch_completed_fixtures(
        league_id=39,
        season=2025,
        start_at=datetime(2026, 1, 1, 2, tzinfo=timezone(timedelta(hours=2))),
        end_at=datetime(2026, 1, 3, 2, tzinfo=timezone(timedelta(hours=2))),
    )

    assert result == {"response": []}
    transport.get_json.assert_called_once_with(
        "https://v3.football.api-sports.io/fixtures?"
        "league=39&season=2025&from=2026-01-01&to=2026-01-03&status=FT&timezone=UTC",
        headers={"x-apisports-key": "secret"},
        timeout=10.0,
    )


@pytest.mark.parametrize("field,value", [("league_id", True), ("league_id", 1.5), ("season", "2025")])
def test_fetch_completed_fixtures_rejects_non_integer_scope(field: str, value: object) -> None:
    arguments = {
        "league_id": 39,
        "season": 2025,
        "start_at": datetime(2026, 1, 1, tzinfo=UTC),
        "end_at": datetime(2026, 1, 2, tzinfo=UTC),
    }
    arguments[field] = value
    with pytest.raises(ValueError, match=field):
        ApiFootballClient(Mock(), "secret").fetch_completed_fixtures(**arguments)  # type: ignore[arg-type]
