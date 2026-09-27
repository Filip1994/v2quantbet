from h2h.quantlab.card_lab.settlement_contract import (
    API_FOOTBALL_TOTAL_CARDS_BET_ID,
    SETTLEMENT_CONTRACT_VERSION,
    card_settlement_contract_status,
)


def test_total_cards_identity_is_known_but_not_pick_authorized() -> None:
    status = card_settlement_contract_status(
        provider_bet_id=119,
        provider_bet_name="Total Cards",
        bookmaker_id=8,
    )

    assert API_FOOTBALL_TOTAL_CARDS_BET_ID == 119
    assert status.contract_version == SETTLEMENT_CONTRACT_VERSION
    assert status.supported is False
    assert status.status == "UNVERIFIED_BOOKMAKER_RULES"


def test_unknown_card_market_identity_fails_closed() -> None:
    status = card_settlement_contract_status(
        provider_bet_id=120,
        provider_bet_name="Total Cards",
        bookmaker_id=8,
    )

    assert status.supported is False
    assert status.status == "UNSUPPORTED_MARKET_IDENTITY"
