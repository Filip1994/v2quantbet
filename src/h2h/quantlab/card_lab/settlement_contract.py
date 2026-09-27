"""CardLab settlement-contract registry.

CardLab may observe many provider markets, but it must not create a shadow PICK unless
the sportsbook settlement semantics for that exact market/bookmaker pair are explicitly
verified. This prevents a measurable-looking P&L from being calculated against an
ambiguous card-count rule.
"""

from __future__ import annotations

from dataclasses import dataclass


SETTLEMENT_CONTRACT_VERSION = "CARDLAB_1XBET_TOTAL_CARDS_SETTLEMENT_V1"
API_FOOTBALL_CARDS_OVER_UNDER_BET_ID = 80


@dataclass(frozen=True, slots=True)
class CardSettlementContractStatus:
    provider_bet_id: int
    provider_bet_name: str
    bookmaker_id: int
    contract_version: str
    supported: bool
    status: str
    reason: str

    def payload(self) -> dict[str, object]:
        return {
            "provider_bet_id": self.provider_bet_id,
            "provider_bet_name": self.provider_bet_name,
            "bookmaker_id": self.bookmaker_id,
            "contract_version": self.contract_version,
            "supported": self.supported,
            "status": self.status,
            "reason": self.reason,
        }


def card_settlement_contract_status(
    *,
    provider_bet_id: int,
    provider_bet_name: str,
    bookmaker_id: int,
) -> CardSettlementContractStatus:
    """Return settlement authority for one exact CardLab market/bookmaker pair.

    Production market inventory identifies API-Football bet 80 as "Cards Over/Under"
    for 1xBet. CardLab authorizes only that exact market identity and bookmaker.
    """
    name = " ".join(str(provider_bet_name).strip().casefold().split())
    if provider_bet_id == API_FOOTBALL_CARDS_OVER_UNDER_BET_ID and name == "cards over/under":
        if bookmaker_id == 11:
            return CardSettlementContractStatus(
                provider_bet_id=provider_bet_id,
                provider_bet_name=provider_bet_name,
                bookmaker_id=bookmaker_id,
                contract_version=SETTLEMENT_CONTRACT_VERSION,
                supported=True,
                status="VERIFIED_1XBET_TARGET",
                reason=(
                    "1xBet Cards Over/Under: regular time including stoppage time; extra time excluded; "
                    "cards count only when shown to a player on the pitch; a second bookable offence "
                    "counts as one card event and a player contributes at most two cards."
                ),
            )
        return CardSettlementContractStatus(
            provider_bet_id=provider_bet_id,
            provider_bet_name=provider_bet_name,
            bookmaker_id=bookmaker_id,
            contract_version=SETTLEMENT_CONTRACT_VERSION,
            supported=False,
            status="UNSUPPORTED_CARDLAB_BOOKMAKER",
            reason="CardLab V5 accepts Cards Over/Under only from 1xBet.",
        )
    return CardSettlementContractStatus(
        provider_bet_id=provider_bet_id,
        provider_bet_name=provider_bet_name,
        bookmaker_id=bookmaker_id,
        contract_version=SETTLEMENT_CONTRACT_VERSION,
        supported=False,
        status="UNSUPPORTED_MARKET_IDENTITY",
        reason="Market identity is not in the canonical CardLab settlement registry.",
    )
