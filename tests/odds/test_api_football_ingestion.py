from unittest.mock import Mock

import pytest

from h2h.domain.fixture_identity import api_football_fixture_identity
from h2h.domain.odds import Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError
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
                        "id": 8,
                        "name": "bet365",
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

    payloads = tuple(
        iter_api_football_quote_payloads(
            response,
            fixture_identity=api_football_fixture_identity(1493129),
        )
    )

    assert len(payloads) == 2
    assert payloads[0] == {
        "fixture": {"id": 1493129},
        "bookmaker": {"id": 8, "name": "bet365"},
        "bet": {"id": 8, "name": "Both Teams Score"},
        "value": {"value": "Yes", "odd": "2.20"},
        "update": None,
    }
    assert payloads[1]["value"] == {"value": "No", "odd": "1.62"}


def test_unfiltered_response_skips_books_outside_the_hard_allowlist() -> None:
    response = {
        "response": [
            {
                "fixture": {"id": 1493129},
                "bookmakers": [
                    {
                        "id": 999,
                        "name": "Unknown",
                        "bets": [
                            {
                                "id": 8,
                                "values": [
                                    {"value": "Yes", "odd": "9.00"},
                                    {"value": "No", "odd": "1.01"},
                                ],
                            }
                        ],
                    },
                    {
                        "id": 34,
                        "name": "Superbet",
                        "bets": [
                            {
                                "id": 8,
                                "values": [
                                    {"value": "Yes", "odd": "2.10"},
                                    {"value": "No", "odd": "1.80"},
                                ],
                            }
                        ],
                    },
                ],
            }
        ]
    }

    payloads = tuple(
        iter_api_football_quote_payloads(
            response, fixture_identity=api_football_fixture_identity(1493129)
        )
    )

    assert len(payloads) == 2
    assert {payload["bookmaker"]["id"] for payload in payloads} == {34}


def test_ingests_api_football_quotes() -> None:
    response = {
        "response": [
            {
                "fixture": {"id": 1493129},
                "bookmakers": [
                    {
                        "id": 8,
                        "name": "bet365",
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

    quotes = ingest_api_football_odds(
        response,
        fixture_identity=api_football_fixture_identity(1493129),
    )

    assert len(quotes) == 2
    assert quotes[0].market is Market.BTTS
    assert quotes[0].fixture_id == "api-football:1493129"
    assert quotes[0].selection is Selection.YES
    assert quotes[1].selection is Selection.NO


def test_builds_api_football_market_snapshot() -> None:
    response = {
        "response": [
            {
                "fixture": {"id": 1493129},
                "bookmakers": [
                    {
                        "id": 8,
                        "name": "bet365",
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

    snapshots = build_api_football_market_snapshots(
        response,
        fixture_identity=api_football_fixture_identity(1493129),
    )

    assert len(snapshots) == 1
    assert snapshots[0].fixture_id == "api-football:1493129"
    assert snapshots[0].bookmaker_id == 8
    assert snapshots[0].market is Market.BTTS
    assert len(snapshots[0].quotes) == 2


def test_skips_malformed_provider_branches() -> None:
    response = {
        "response": [
            {"fixture": {"id": 1}, "bookmakers": "invalid"},
            {
                "fixture": {"id": 1},
                "bookmakers": [{"id": 8, "name": "Bet365", "bets": "invalid"}],
            },
            {"fixture": {"id": 1}, "bookmakers": []},
        ]
    }

    assert (
        tuple(
            iter_api_football_quote_payloads(
                response,
                fixture_identity=api_football_fixture_identity(1),
            )
        )
        == ()
    )


def test_rejects_mismatched_fixture_record_with_no_bookmakers() -> None:
    response = {"response": [{"fixture": {"id": 999}, "bookmakers": []}]}

    with pytest.raises(QuoteNormalizationError, match="does not match"):
        ingest_api_football_odds(
            response,
            fixture_identity=api_football_fixture_identity(123),
        )


def test_rejects_missing_fixture_id_with_no_quote_branches() -> None:
    response = {"response": [{"fixture": {}, "bookmakers": []}]}

    with pytest.raises(QuoteNormalizationError, match="fixture.id"):
        ingest_api_football_odds(
            response,
            fixture_identity=api_football_fixture_identity(123),
        )


def test_rejects_malformed_fixture_id_with_no_quote_branches() -> None:
    response = {"response": [{"fixture": {"id": "123"}, "bookmakers": []}]}

    with pytest.raises(QuoteNormalizationError, match="fixture.id"):
        ingest_api_football_odds(
            response,
            fixture_identity=api_football_fixture_identity(123),
        )


def test_rejects_mixed_matching_and_mismatched_fixture_records_before_adapting() -> None:
    response = {
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
                                "values": [{"value": "Yes", "odd": "2.20"}],
                            }
                        ],
                    }
                ],
            },
            {"fixture": {"id": 999}, "bookmakers": []},
        ]
    }
    adapter = Mock()

    with pytest.raises(QuoteNormalizationError, match="does not match"):
        ingest_api_football_odds(
            response,
            fixture_identity=api_football_fixture_identity(123),
            adapter=adapter,
        )

    adapter.adapt.assert_not_called()


def test_matching_fixture_with_no_supported_quote_branches_yields_no_quotes() -> None:
    response = {"response": [{"fixture": {"id": 123}, "bookmakers": []}]}

    assert (
        ingest_api_football_odds(
            response,
            fixture_identity=api_football_fixture_identity(123),
        )
        == ()
    )


def test_unsupported_bet_branches_are_skipped_before_adapting() -> None:
    response = {
        "response": [
            {
                "fixture": {"id": 123},
                "bookmakers": [
                    {
                        "id": 8,
                        "name": "Bet365",
                        "update": "2026-09-15T12:00:00+00:00",
                        "bets": [
                            {"id": 1, "values": [{"value": "Home", "odd": "2.1"}]},
                            {
                                "id": 5,
                                "values": [{"value": "Over 1.5", "odd": "1.4"}],
                            },
                            {"id": 8, "values": [{"value": "Yes", "odd": "2.2"}]},
                        ],
                    }
                ],
            }
        ]
    }

    quotes = ingest_api_football_odds(
        response,
        fixture_identity=api_football_fixture_identity(123),
    )

    assert len(quotes) == 1
    assert quotes[0].market.value == "BTTS"
