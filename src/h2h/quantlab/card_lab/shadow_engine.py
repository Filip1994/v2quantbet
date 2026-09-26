"""CardLab V1 shadow pick engine."""

from __future__ import annotations

from typing import Any

from h2h.quantlab.reference_shadow_engine import (
    ReferenceShadowPickEngine,
    ReferenceShadowPolicy,
)


POLICY_VERSION = "CARDLAB_REFERENCE_CONTEXT_POLICY_V1"
MODEL_VERSION = "CROSS_BOOK_FAIR_REFERENCE_CARD_CONTEXT_V1"


class CardLabShadowPickEngine(ReferenceShadowPickEngine):
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
