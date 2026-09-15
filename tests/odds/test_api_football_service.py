from unittest.mock import Mock

from h2h.domain.fixture_identity import api_football_fixture_identity
from h2h.odds.api_football_service import ApiFootballOddsService


def test_fetch_quotes_delegates_to_client_and_ingestion() -> None:
    client = Mock()
    client.fetch_odds.return_value = {"response": []}
    service = ApiFootballOddsService(client)

    result = service.fetch_quotes(
        fixture_identity=api_football_fixture_identity(42)
    )

    assert result == ()
    client.fetch_odds.assert_called_once_with(fixture_id=42)


def test_fetch_market_snapshots_delegates_to_client_and_ingestion() -> None:
    client = Mock()
    client.fetch_odds.return_value = {"response": []}
    service = ApiFootballOddsService(client)

    result = service.fetch_market_snapshots(
        fixture_identity=api_football_fixture_identity(42)
    )

    assert result == ()
    client.fetch_odds.assert_called_once_with(fixture_id=42)


def test_fetch_quotes_uses_numeric_transport_and_canonical_quote_identity() -> None:
    client = Mock()
    client.fetch_odds.return_value = {
        "response": [
            {
                "fixture": {"id": 123},
                "bookmakers": [
                    {
                        "id": 8,
                        "name": "Bet365",
                        "update": "2026-09-15T12:00:00+00:00",
                        "bets": [
                            {
                                "id": 8,
                                "values": [
                                    {"value": "Yes", "odd": "2.20"},
                                    {"value": "No", "odd": "1.62"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    service = ApiFootballOddsService(client)

    quotes = service.fetch_quotes(
        fixture_identity=api_football_fixture_identity(123)
    )

    client.fetch_odds.assert_called_once_with(fixture_id=123)
    assert {quote.fixture_id for quote in quotes} == {"api-football:123"}
