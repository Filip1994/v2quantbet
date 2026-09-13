from h2h.domain.odds import Market, Selection
from h2h.odds.api_football_ingestion import (
    build_api_football_market_snapshots,
    ingest_api_football_odds,
    iter_api_football_quote_payloads,
)


def test_flattens_api_football_odds_response() -> None:
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
                    }
                ],
            }
        ]
    }

    payloads = tuple(iter_api_football_quote_payloads(response))

    assert len(payloads) == 2
    assert payloads[0] == {
        "fixture": {"id": 1493129},
        "bookmaker": {"id": 7, "name": "William Hill"},
        "bet": {"id": 8, "name": "Both Teams Score"},
        "value": {"value": "Yes", "odd": "2.20"},
        "update": None,
    }
    assert payloads[1]["value"] == {"value": "No", "odd": "1.62"}


def test_ingests_api_football_quotes() -> None:
    response = {
        "response": [
            {
                "fixture": {"id": 1493129},
                "bookmakers": [
                    {
                        "id": 7,
                        "name": "William Hill",
                        "update": "2026-09-13T20:03:16+00:00",
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

    quotes = ingest_api_football_odds(response)

    assert len(quotes) == 2
    assert quotes[0].market is Market.BTTS
    assert quotes[0].selection is Selection.YES
    assert quotes[1].selection is Selection.NO


def test_builds_api_football_market_snapshot() -> None:
    response = {
        "response": [
            {
                "fixture": {"id": 1493129},
                "bookmakers": [
                    {
                        "id": 7,
                        "name": "William Hill",
                        "update": "2026-09-13T20:03:16+00:00",
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

    snapshots = build_api_football_market_snapshots(response)

    assert len(snapshots) == 1
    assert snapshots[0].fixture_id == "1493129"
    assert snapshots[0].bookmaker_id == 7
    assert snapshots[0].market is Market.BTTS
    assert len(snapshots[0].quotes) == 2


def test_skips_malformed_provider_branches() -> None:
    response = {
        "response": [
            {"fixture": {"id": 1}, "bookmakers": "invalid"},
            "invalid-fixture",
            {"fixture": {"id": 2}, "bookmakers": []},
        ]
    }

    assert tuple(iter_api_football_quote_payloads(response)) == ()
