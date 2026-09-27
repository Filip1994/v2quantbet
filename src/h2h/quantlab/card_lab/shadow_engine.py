"""CardLab V1 shadow pick engine."""

from __future__ import annotations

from typing import Any

from h2h.quantlab.card_lab.settlement_contract import card_settlement_contract_status
from h2h.quantlab.reference_shadow_engine import (
    ReferenceShadowPickEngine,
    ReferenceShadowPolicy,
)


POLICY_VERSION = "CARDLAB_REFERENCE_CONTEXT_POLICY_V3_1XBET_ONLY"
MODEL_VERSION = "CROSS_BOOK_FAIR_REFERENCE_CARD_CONTEXT_V1"


class CardLabShadowPickEngine(ReferenceShadowPickEngine):
    def _settlement_contract_status(self, pair: dict[str, Any]) -> dict[str, Any]:
        return card_settlement_contract_status(
            provider_bet_id=int(pair["provider_bet_id"]),
            provider_bet_name=str(pair["provider_bet_name"]),
            bookmaker_id=int(pair["bookmaker_id"]),
        ).payload()

    def __init__(self, repository: Any) -> None:
        super().__init__(
            repository,
            policy=ReferenceShadowPolicy(
                lab="CARD",
                market_key="TOTAL_CARDS",
                policy_version=POLICY_VERSION,
                model_name="Cross-book fair reference + CardLab referee gate",
                model_version=MODEL_VERSION,
            ),
        )
