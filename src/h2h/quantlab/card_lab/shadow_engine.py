"""CardLab V1 shadow-only probability and pick engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from h2h.quantlab.count_shadow import (
    CountLabShadowPickEngine,
    CountShadowPolicy,
    ModelMean,
    market_tokens,
)


POLICY_VERSION = "CARDLAB_SHADOW_POLICY_V1"
MODEL_NAME = "Referee Card Poisson"
MODEL_VERSION = "CARD_REFEREE_POISSON_V1"


class CardLabShadowPickEngine(CountLabShadowPickEngine):
    """Referee-card Poisson baseline guarded by the frozen CardLab context snapshot.

    V1 deliberately does not invent coefficients for table pressure, rivalry or importance.
    Those timestamp-safe features are required/recorded as context and can later be calibrated
    against settled shadow evidence. The numeric count mean is the observed referee card rate.
    """

    lab = "CARD"
    policy_version = POLICY_VERSION
    model_name = MODEL_NAME
    model_version = MODEL_VERSION

    def __init__(self, repository: Any) -> None:
        super().__init__(
            repository,
            policy=CountShadowPolicy(
                min_edge=0.05,
                min_expected_value=0.05,
                min_odds=1.45,
                max_odds=3.50,
                max_quote_age_seconds=13 * 60 * 60,
                min_seconds_to_kickoff=15 * 60,
                flat_stake_minor=10_000,
            ),
        )

    def market_allowed(self, provider_bet_name: str) -> bool:
        tokens = market_tokens(provider_bet_name)
        if not ({"card", "cards"} & tokens):
            return False
        blocked = {
            "home",
            "away",
            "team",
            "handicap",
            "asian",
            "points",
            "booking",
            "bookings",
            "yellow",
            "red",
            "first",
            "second",
            "half",
            "1st",
            "2nd",
        }
        if tokens & blocked:
            return False
        return "total" in tokens or "over" in tokens or "under" in tokens or len(tokens) <= 3

    def model_mean(self, fixture: dict[str, Any], decision_at: datetime) -> ModelMean:
        snapshot = self._repository.latest_card_feature(
            str(fixture["fixture_id"]),
            decision_at=decision_at,
        )
        if snapshot is None:
            return ModelMean(
                None,
                MODEL_NAME,
                MODEL_VERSION,
                "NO_CARD_FEATURE_SNAPSHOT",
                {},
            )

        card_rate = snapshot.get("referee_card_rate")
        card_n = int(snapshot.get("referee_sample_size") or 0)
        foul_rate = snapshot.get("referee_foul_rate")
        foul_n = int(snapshot.get("referee_foul_sample_size") or 0)
        pressure = snapshot.get("table_pressure")
        importance = snapshot.get("match_importance")

        if card_rate is None or card_n < 5:
            return ModelMean(
                None,
                MODEL_NAME,
                MODEL_VERSION,
                "INSUFFICIENT_REFEREE_CARD_HISTORY",
                {
                    "referee": snapshot.get("referee"),
                    "referee_sample_size": card_n,
                    "minimum_referee_sample": 5,
                },
            )
        if foul_rate is None or foul_n < 5:
            return ModelMean(
                None,
                MODEL_NAME,
                MODEL_VERSION,
                "INSUFFICIENT_REFEREE_FOUL_HISTORY",
                {
                    "referee": snapshot.get("referee"),
                    "referee_foul_sample_size": foul_n,
                    "minimum_referee_sample": 5,
                },
            )
        if pressure is None or importance is None:
            return ModelMean(
                None,
                MODEL_NAME,
                MODEL_VERSION,
                "INCOMPLETE_CARD_CONTEXT",
                {
                    "table_pressure_available": pressure is not None,
                    "match_importance_available": importance is not None,
                },
            )

        return ModelMean(
            float(card_rate),
            MODEL_NAME,
            MODEL_VERSION,
            None,
            {
                "referee": snapshot.get("referee"),
                "referee_card_rate": float(card_rate),
                "referee_sample_size": card_n,
                "referee_foul_rate": float(foul_rate),
                "referee_foul_sample_size": foul_n,
                "derby_rivalry_indicator": snapshot.get("derby_rivalry_indicator"),
                "table_pressure": float(pressure),
                "match_importance": float(importance),
                "feature_version": snapshot.get("feature_version"),
                "probability_driver": "referee_card_rate",
                "context_role": "eligibility_and_audit_only",
                "calibration_status": "UNCALIBRATED_CONTEXT_COEFFICIENTS_NOT_USED",
            },
        )
