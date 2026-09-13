from h2h.odds.api_football_ingestion import iter_api_football_quote_payloads


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


def test_skips_malformed_provider_branches() -> None:
    response = {
        "response": [
            {"fixture": {"id": 1}, "bookmakers": "invalid"},
            "invalid-fixture",
            {"fixture": {"id": 2}, "bookmakers": []},
        ]
    }

    assert tuple(iter_api_football_quote_payloads(response)) == ()
