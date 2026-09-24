from datetime import UTC, datetime

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.odds.api_football_live import parse_api_football_live_quotes


NOW = datetime(2026, 9, 24, 1, 50, tzinfo=UTC)


def _payload():
    return {
        "response": [
            {
                "fixture": {"id": 42},
                "status": {"stopped": False, "blocked": False, "finished": True},
                "update": NOW.isoformat(),
                "odds": [
                    {
                        "id": 25,
                        "name": "Match Goals",
                        "values": [
                            {
                                "value": "Over",
                                "odd": "2.05",
                                "handicap": "2.5",
                                "main": True,
                                "suspended": False,
                            },
                            {
                                "value": "Under",
                                "odd": "1.80",
                                "handicap": "2.5",
                                "main": True,
                                "suspended": False,
                            },
                            {
                                "value": "Over",
                                "odd": "4.00",
                                "handicap": "3.5",
                                "main": False,
                                "suspended": False,
                            },
                        ],
                    },
                    {
                        "id": 69,
                        "name": "Both Teams to Score",
                        "values": [
                            {"value": "Yes", "odd": "1.91", "suspended": False},
                            {"value": "No", "odd": "1.91", "suspended": False},
                        ],
                    },
                ],
            }
        ]
    }


def test_live_parser_maps_only_exact_supported_markets() -> None:
    quotes = parse_api_football_live_quotes(_payload(), fixture_id=42)

    assert {(q.market, q.selection, q.odd) for q in quotes} == {
        (Market.OU_25, Selection.OVER, 2.05),
        (Market.OU_25, Selection.UNDER, 1.80),
        (Market.BTTS, Selection.YES, 1.91),
        (Market.BTTS, Selection.NO, 1.91),
    }
    assert {q.observed_at for q in quotes} == {NOW}
    assert {q.source for q in quotes} == {"api-football-live"}


def test_live_parser_fails_closed_on_bet_id_name_mismatch() -> None:
    payload = _payload()
    payload["response"][0]["odds"][1]["name"] = "Match Goals"

    with pytest.raises(QuoteNormalizationError, match="id/name mismatch"):
        parse_api_football_live_quotes(payload, fixture_id=42)


def test_live_parser_skips_suspended_or_blocked_prices() -> None:
    payload = _payload()
    payload["response"][0]["odds"][0]["values"][0]["suspended"] = True
    quotes = parse_api_football_live_quotes(payload, fixture_id=42)
    assert (Market.OU_25, Selection.OVER) not in {
        (q.market, q.selection) for q in quotes
    }

    payload = _payload()
    payload["response"][0]["status"]["blocked"] = True
    assert parse_api_football_live_quotes(payload, fixture_id=42) == ()
