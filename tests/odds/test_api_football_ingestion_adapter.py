from datetime import UTC, datetime

from h2h.domain.odds import Market, Selection
from h2h.odds import ingest_api_football_odds


def test_ingests_api_football_response_into_canonical_quotes() -> None:
    response = {
        "response": [
            {
                "fixture": {"id": 1493129},
                "bookmakers": [
                    {
                        "id": 7,
                        "name": "William Hill",
                        "bets": [
                            {
                                "id": 8,
                                "name": "Both Teams Score",
                                "values": [
                                    {"value": "Yes", "odd": "2.20"},
                                    {"value": "No", "odd": "1.62"},
                                ],
                            }
                        ],
                        "update": "2026-09-13T20:03:16+00:00",
                    }
                ],
            }
        ]
    }

    quotes = ingest_api_football_odds(response)

    assert len(quotes) == 2
    assert quotes[0].fixture_id == "1493129"
    assert quotes[0].bookmaker_name == "William Hill"
    assert quotes[0].market is Market.BTTS
    assert quotes[0].selection is Selection.YES
    assert quotes[0].odd == 2.20
    assert quotes[0].observed_at == datetime(2026, 9, 13, 20, 3, 16, tzinfo=UTC)
    assert quotes[1].selection is Selection.NO
    assert quotes[1].odd == 1.62
