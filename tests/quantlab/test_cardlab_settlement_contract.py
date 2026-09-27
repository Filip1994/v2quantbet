from h2h.quantlab.card_lab.settlement_contract import (
    API_FOOTBALL_TOTAL_CARDS_BET_ID,
    SETTLEMENT_CONTRACT_VERSION,
    card_settlement_contract_status,
)


def test_1xbet_total_cards_is_pick_authorized() -> None:
    status = card_settlement_contract_status(
        provider_bet_id=119,
        provider_bet_name="Total Cards",
        bookmaker_id=11,
    )

    assert API_FOOTBALL_TOTAL_CARDS_BET_ID == 119
    assert status.contract_version == SETTLEMENT_CONTRACT_VERSION
    assert status.supported is True
    assert status.status == "VERIFIED_1XBET_TARGET"


def test_bet365_total_cards_is_not_a_cardlab_bookmaker() -> None:
    status = card_settlement_contract_status(
        provider_bet_id=119,
        provider_bet_name="Total Cards",
        bookmaker_id=8,
    )

    assert status.supported is False
    assert status.status == "UNSUPPORTED_CARDLAB_BOOKMAKER"


def test_unknown_card_market_identity_fails_closed() -> None:
    status = card_settlement_contract_status(
        provider_bet_id=120,
        provider_bet_name="Total Cards",
        bookmaker_id=11,
    )

    assert status.supported is False
    assert status.status == "UNSUPPORTED_MARKET_IDENTITY"
