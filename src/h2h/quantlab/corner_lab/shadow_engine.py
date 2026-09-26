"""CornerLab V1 shadow pick engine."""

from __future__ import annotations

from typing import Any

from h2h.quantlab.reference_shadow_engine import (
    ReferenceShadowPickEngine,
    ReferenceShadowPolicy,
)


POLICY_VERSION = "CORNERLAB_REFERENCE_POLICY_V1"
MODEL_VERSION = "CROSS_BOOK_FAIR_REFERENCE_V1"


class CornerLabShadowPickEngine(ReferenceShadowPickEngine):
    def __init__(self, repository: Any) -> None:
        super().__init__(
            repository,
            policy=ReferenceShadowPolicy(
                lab="CORNER",
                market_key="TOTAL_CORNERS",
                policy_version=POLICY_VERSION,
                model_name="Cross-book fair reference",
                model_version=MODEL_VERSION,
            ),
        )
