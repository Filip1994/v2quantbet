from datetime import UTC, datetime

from h2h.quantlab.card_lab.settlement import (
    SETTLEMENT_RULE_VERSION,
    parse_1xbet_card_events,
    settle_card_shadow_bet,
)


NOW = datetime(2026, 9, 27, 18, 0, tzinfo=UTC)


def _events_payload():
    return {
        "errors": [],
        "response": [
            {
                "time": {"elapsed": 20, "extra": None},
                "team": {"id": 1, "name": "Home"},
                "player": {"id": 101, "name": "Player A"},
                "type": "Card",
                "detail": "Yellow Card",
            },
            {
                "time": {"elapsed": 70, "extra": None},
                "team": {"id": 1, "name": "Home"},
                "player": {"id": 101, "name": "Player A"},
                "type": "Card",
                "detail": "Yellow-Red Card",
            },
            {
                "time": {"elapsed": 50, "extra": None},
                "team": {"id": 2, "name": "Away"},
                "player": {"id": 202, "name": "Player B"},
                "type": "Card",
                "detail": "Red Card",
            },
            {
                "time": {"elapsed": 95, "extra": None},
                "team": {"id": 2, "name": "Away"},
                "player": {"id": 203, "name": "Extra Time"},
                "type": "Card",
                "detail": "Yellow Card",
            },
            {
                "time": {"elapsed": 80, "extra": None},
                "team": {"id": 2, "name": "Away"},
                "player": {"id": None, "name": "Unknown"},
                "type": "Card",
                "detail": "Yellow Card",
            },
        ],
    }


def test_parse_1xbet_card_events_caps_player_at_two_and_excludes_extra_time():
    observation = parse_1xbet_card_events(
        _events_payload(),
        fixture_id="api-football:123",
        provider_fixture_id=123,
        captured_at=NOW,
    )

    assert observation.settlement_rule_version == SETTLEMENT_RULE_VERSION
    assert observation.total_cards_1xbet == 3
    assert observation.qualifying_event_count == 3
    assert len(observation.event_payload) == 3


def test_settle_1xbet_total_cards_over_win():
    observation = parse_1xbet_card_events(
        _events_payload(),
        fixture_id="api-football:123",
        provider_fixture_id=123,
        captured_at=NOW,
    )
    settlement = settle_card_shadow_bet(
        {
            "shadow_bet_id": "quantlab-shadow-v1:" + "a" * 64,
            "fixture_id": "api-football:123",
            "bookmaker_id": 11,
            "provider_bet_id": 80,
            "market_key": "TOTAL_CARDS",
            "selection": "OVER",
            "line": 2.5,
            "odds": 1.9,
            "stake_minor": 10_000,
            "fixture_observation_id": "quantlab-fixture-v1:" + "b" * 64,
            "provider_status": "FT",
            "result_classification": "PLAYED_SETTLEABLE",
            "card_event_observation_id": observation.card_event_observation_id,
            "total_cards_1xbet": observation.total_cards_1xbet,
        },
        settled_at=NOW,
    )

    assert settlement is not None
    assert settlement.outcome == "WIN"
    assert settlement.pnl_minor == 9_000
    assert settlement.result_detail["total_cards_1xbet"] == 3


def test_non_played_card_fixture_voids_without_event_observation():
    settlement = settle_card_shadow_bet(
        {
            "shadow_bet_id": "quantlab-shadow-v1:" + "c" * 64,
            "fixture_id": "api-football:456",
            "bookmaker_id": 11,
            "provider_bet_id": 80,
            "market_key": "TOTAL_CARDS",
            "selection": "UNDER",
            "line": 4.5,
            "odds": 1.8,
            "stake_minor": 10_000,
            "fixture_observation_id": "quantlab-fixture-v1:" + "d" * 64,
            "provider_status": "CANC",
            "result_classification": "NON_PLAYED_VOIDABLE",
            "card_event_observation_id": None,
            "total_cards_1xbet": None,
        },
        settled_at=NOW,
    )

    assert settlement is not None
    assert settlement.outcome == "VOID"
    assert settlement.pnl_minor == 0
