"""CardLab settlement-contract registry.

CardLab may observe many provider markets, but it must not create a shadow PICK unless
the sportsbook settlement semantics for that exact market/bookmaker pair are explicitly
verified. This prevents a measurable-looking P&L from being calculated against an
ambiguous card-count rule.
"""

from __future__ import annotations

from dataclasses import dataclass


SETTLEMENT_CONTRACT_VERSION = "CARDLAB_SETTLEMENT_CONTRACT_V1"
API_FOOTBALL_TOTAL_CARDS_BET_ID = 119


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

    API-Football's pre-match catalog identifies bet 119 as Total Cards. The feed
    preserves that market identity, but it does not define the sportsbook-specific
    weighting or treatment of yellow, second-yellow and red cards. Until those rules
    are separately verified for a bookmaker, the market is research-visible but cannot
    become a CardLab shadow PICK.
    """
    name = " ".join(str(provider_bet_name).strip().casefold().split())
    if provider_bet_id == API_FOOTBALL_TOTAL_CARDS_BET_ID and name == "total cards":
        return CardSettlementContractStatus(
            provider_bet_id=provider_bet_id,
            provider_bet_name=provider_bet_name,
            bookmaker_id=bookmaker_id,
            contract_version=SETTLEMENT_CONTRACT_VERSION,
            supported=False,
            status="UNVERIFIED_BOOKMAKER_RULES",
            reason=(
                "Total Cards market identity is known, but yellow/red/second-yellow "
                "settlement weighting is not yet verified for this bookmaker."
            ),
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
