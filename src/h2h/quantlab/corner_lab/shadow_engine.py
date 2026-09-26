"""CornerLab V1 shadow-only probability and pick engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from h2h.quantlab.count_shadow import (
    CountLabShadowPickEngine,
    ModelMean,
    market_tokens,
    mean,
)


POLICY_VERSION = "CORNERLAB_SHADOW_POLICY_V1"
MODEL_NAME = "Corner Poisson Form"
MODEL_VERSION = "CORNER_POISSON_FORM_V1"


class CornerLabShadowPickEngine(CountLabShadowPickEngine):
    """Poisson total-corners baseline from timestamp-safe stored team corner history."""

    lab = "CORNER"
    policy_version = POLICY_VERSION
    model_name = MODEL_NAME
    model_version = MODEL_VERSION

    def market_allowed(self, provider_bet_name: str) -> bool:
        tokens = market_tokens(provider_bet_name)
        if not ({"corner", "corners"} & tokens):
            return False
        blocked = {
            "home",
            "away",
            "team",
            "handicap",
            "asian",
            "race",
            "exact",
            "odd",
            "even",
            "first",
            "second",
            "half",
            "1st",
            "2nd",
        }
        if tokens & blocked:
            return False
        return "total" in tokens or "over" in tokens or "under" in tokens or len(tokens) <= 3

    @staticmethod
    def _sample(
        history: tuple[dict[str, Any], ...],
        *,
        prefer_home: bool,
    ) -> tuple[dict[str, Any], ...]:
        venue = tuple(
            item for item in history if bool(item.get("was_home")) is prefer_home
        )
        return venue if len(venue) >= 3 else history

    def model_mean(self, fixture: dict[str, Any], decision_at: datetime) -> ModelMean:
        home_team_id = fixture.get("home_team_id")
        away_team_id = fixture.get("away_team_id")
        if home_team_id is None or away_team_id is None:
            return ModelMean(
                None,
                MODEL_NAME,
                MODEL_VERSION,
                "MISSING_FIXTURE_TEAM_IDS",
                {},
            )

        home_history = tuple(
            self._repository.team_corner_history(
                int(home_team_id),
                before=decision_at,
                limit=10,
            )
        )
        away_history = tuple(
            self._repository.team_corner_history(
                int(away_team_id),
                before=decision_at,
                limit=10,
            )
        )
        if len(home_history) < 5 or len(away_history) < 5:
            return ModelMean(
                None,
                MODEL_NAME,
                MODEL_VERSION,
                "INSUFFICIENT_CORNER_HISTORY",
                {
                    "home_sample_size": len(home_history),
                    "away_sample_size": len(away_history),
                    "minimum_per_team": 5,
                },
            )

        home_sample = self._sample(home_history, prefer_home=True)
        away_sample = self._sample(away_history, prefer_home=False)
        home_for = mean(item["corners_for"] for item in home_sample)
        home_against = mean(item["corners_against"] for item in home_sample)
        away_for = mean(item["corners_for"] for item in away_sample)
        away_against = mean(item["corners_against"] for item in away_sample)

        expected_home = (home_for + away_against) / 2.0
        expected_away = (away_for + home_against) / 2.0
        total_mean = expected_home + expected_away

        return ModelMean(
            total_mean,
            MODEL_NAME,
            MODEL_VERSION,
            None,
            {
                "home_sample_size": len(home_sample),
                "away_sample_size": len(away_sample),
                "home_total_history": len(home_history),
                "away_total_history": len(away_history),
                "home_corners_for_mean": home_for,
                "home_corners_against_mean": home_against,
                "away_corners_for_mean": away_for,
                "away_corners_against_mean": away_against,
                "expected_home_corners": expected_home,
                "expected_away_corners": expected_away,
                "expected_total_corners": total_mean,
                "venue_split_fallback": {
                    "home": len(home_sample) == len(home_history),
                    "away": len(away_sample) == len(away_history),
                },
            },
        )
