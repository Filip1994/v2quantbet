from unittest.mock import Mock

from h2h.odds.api_football_service import ApiFootballOddsService


def test_fetch_quotes_delegates_to_client_and_ingestion() -> None:
    client = Mock()
    client.fetch_odds.return_value = {"response": []}
    service = ApiFootballOddsService(client)

    result = service.fetch_quotes(fixture_id=42)

    assert result == ()
    client.fetch_odds.assert_called_once_with(fixture_id=42)


def test_fetch_market_snapshots_delegates_to_client_and_ingestion() -> None:
    client = Mock()
    client.fetch_odds.return_value = {"response": []}
    service = ApiFootballOddsService(client)

    result = service.fetch_market_snapshots(fixture_id=42)

    assert result == ()
    client.fetch_odds.assert_called_once_with(fixture_id=42)
