"""GoalLab DC+ Pro Structural V1 market evaluation.

The structural model owns probabilities. Bookmaker odds are used only for de-vig market
probability, edge and expected value. V1 remains evaluation-only until its holdout and
leakage audit are recorded; qualifying value is therefore PASS/STRUCTURAL_VALUE_SIGNAL_ONLY.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from h2h.quantlab.goal_lab.model import MODEL_NAME, GoalStructuralModelService
from h2h.quantlab.goal_lab.shadow_engine import GoalDecision, GoalEngineResult
from h2h.quantlab.scope import goal_scope


POLICY_VERSION = "GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V1"
MIN_EDGE = 0.03
MIN_EXPECTED_VALUE = 0.03
MIN_ODDS = 1.40
MAX_ODDS = 4.00
MAX_QUOTE_AGE_SECONDS = 13 * 60 * 60
MIN_SECONDS_TO_KICKOFF = 15 * 60


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _fingerprint(payload: object) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class StructuralGoalPolicy:
    min_edge: float = MIN_EDGE
    min_expected_value: float = MIN_EXPECTED_VALUE
    min_odds: float = MIN_ODDS
    max_odds: float = MAX_ODDS
    max_quote_age_seconds: int = MAX_QUOTE_AGE_SECONDS
    min_seconds_to_kickoff: int = MIN_SECONDS_TO_KICKOFF
    version: str = POLICY_VERSION


class GoalLabStructuralShadowEngine:
    """Run structural probabilities without granting V1 shadow-pick authority."""

    def __init__(self, repository: Any, *, policy: StructuralGoalPolicy | None = None) -> None:
        self._repository = repository
        self._model = GoalStructuralModelService(repository)
        self._policy = policy or StructuralGoalPolicy()

    @staticmethod
    def _scope_kwargs(fixture: dict[str, Any]) -> dict[str, object]:
        return {
            "country": fixture.get("country"),
            "competition_name": fixture.get("competition_name"),
            "competition_type": fixture.get("competition_type"),
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
        }

    def _fixture_pass(
        self,
        fixture: dict[str, Any],
        now: datetime,
        *,
        reason: str,
        model_version: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> GoalEngineResult:
        payload = dict(details or {})
        evidence = _fingerprint(
            {
                "fixture_id": fixture["fixture_id"],
                "policy_version": self._policy.version,
                "model_version": model_version,
                "reason": reason,
                "details": payload,
            }
        )
        decision = GoalDecision(
            decision_id="quantlab-goal-decision-v1:"
            + _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "policy_version": self._policy.version,
                    "evidence": evidence,
                }
            ),
            fixture_id=str(fixture["fixture_id"]),
            decision_at=now,
            policy_version=self._policy.version,
            model_name=None if model_version is None else MODEL_NAME,
            model_version=model_version,
            bookmaker_id=None,
            bookmaker_name=None,
            provider_bet_id=None,
            provider_bet_name=None,
            market_key=None,
            selection=None,
            line=None,
            selected_observation_id=None,
            companion_observation_id=None,
            quote_observed_at=None,
            odds=None,
            companion_odds=None,
            market_probability=None,
            model_probability=None,
            edge=None,
            expected_value=None,
            decision="PASS",
            reason=reason,
            evidence_fingerprint=evidence,
            details=payload,
        )
        return GoalEngineResult(
            decisions_inserted=int(bool(self._repository.save_goal_decision(decision)))
        )

    @staticmethod
    def _selection_probability(
        probabilities: dict[str, float], market_key: str, selection: str
    ) -> float:
        if market_key == "OU_25":
            key = "OVER_2_5" if selection == "OVER" else "UNDER_2_5"
            value = probabilities[key]
        elif market_key == "BTTS":
            yes = probabilities["BTTS_YES"]
            value = yes if selection == "YES" else 1.0 - yes
        else:
            raise ValueError(f"unsupported GoalLab market {market_key!r}")
        result = float(value)
        if not isfinite(result) or not 0.0 < result < 1.0:
            raise ValueError("DC+ model probability must be finite and inside (0, 1)")
        return result

    def run_fixture(self, fixture: dict[str, Any], *, decision_at: datetime) -> GoalEngineResult:
        now = _utc(decision_at, "decision_at")
        if not goal_scope(**self._scope_kwargs(fixture)).allowed:
            return self._fixture_pass(fixture, now, reason="OUTSIDE_GOAL_SCOPE")

        model_result = self._model.estimate(fixture, decision_at=now)
        if model_result.estimate is None:
            return self._fixture_pass(
                fixture,
                now,
                reason=model_result.reason,
                details=model_result.details,
            )
        estimate = model_result.estimate
        probabilities = estimate.market_probabilities()
        pairs = tuple(
            self._repository.goal_market_pairs(str(fixture["fixture_id"]), decision_at=now)
        )
        if not pairs:
            return self._fixture_pass(
                fixture,
                now,
                reason="NO_COMPLETE_GOAL_MARKET",
                model_version=estimate.model.model_version,
                details=model_result.details,
            )

        kickoff = _utc(fixture["kickoff_at"], "kickoff_at")
        evaluated: list[dict[str, Any]] = []
        for pair in pairs:
            market_key = str(pair["market_key"])
            selections = dict(pair["selections"])
            directions = (
                (("OVER", "UNDER"), ("UNDER", "OVER"))
                if market_key == "OU_25"
                else (("YES", "NO"), ("NO", "YES"))
            )
            for selection, companion_selection in directions:
                selected = selections[selection]
                companion = selections[companion_selection]
                odds = float(selected["odds"])
                companion_odds = float(companion["odds"])
                raw_selected = 1.0 / odds
                raw_companion = 1.0 / companion_odds
                market_probability = raw_selected / (raw_selected + raw_companion)
                model_probability = self._selection_probability(
                    probabilities, market_key, selection
                )
                edge = model_probability - market_probability
                expected_value = model_probability * odds - 1.0
                captured_at = _utc(pair["captured_at"], "captured_at")
                quote_age = (now - captured_at).total_seconds()
                seconds_to_kickoff = (kickoff - now).total_seconds()

                reason: str | None = None
                if seconds_to_kickoff < self._policy.min_seconds_to_kickoff:
                    reason = "KICKOFF_TOO_CLOSE"
                elif quote_age < 0:
                    reason = "QUOTE_FROM_FUTURE"
                elif quote_age > self._policy.max_quote_age_seconds:
                    reason = "STALE_QUOTE"
                elif not self._policy.min_odds <= odds <= self._policy.max_odds:
                    reason = "ODDS_OUTSIDE_RANGE"
                elif edge < self._policy.min_edge:
                    reason = "EDGE_BELOW_MINIMUM"
                elif expected_value < self._policy.min_expected_value:
                    reason = "EV_BELOW_MINIMUM"

                evaluated.append(
                    {
                        "pair": pair,
                        "selection": selection,
                        "companion_selection": companion_selection,
                        "selected": selected,
                        "companion": companion,
                        "odds": odds,
                        "companion_odds": companion_odds,
                        "market_probability": market_probability,
                        "model_probability": model_probability,
                        "edge": edge,
                        "expected_value": expected_value,
                        "quote_age_seconds": quote_age,
                        "seconds_to_kickoff": seconds_to_kickoff,
                        "reason": reason,
                    }
                )

        winners: dict[tuple[str, str, float | None], dict[str, Any]] = {}
        for item in evaluated:
            if item["reason"] is not None:
                continue
            pair = item["pair"]
            line = None if pair.get("line") is None else float(pair["line"])
            key = (str(pair["market_key"]), str(item["selection"]), line)
            current = winners.get(key)
            score = (
                float(item["expected_value"]),
                float(item["edge"]),
                float(item["odds"]),
                -int(pair["bookmaker_id"]),
            )
            if current is None:
                winners[key] = item
                continue
            current_score = (
                float(current["expected_value"]),
                float(current["edge"]),
                float(current["odds"]),
                -int(current["pair"]["bookmaker_id"]),
            )
            if score > current_score:
                winners[key] = item

        inserted = 0
        for item in evaluated:
            pair = item["pair"]
            line = None if pair.get("line") is None else float(pair["line"])
            key = (str(pair["market_key"]), str(item["selection"]), line)
            if item["reason"] is None:
                reason = (
                    "STRUCTURAL_VALUE_SIGNAL_ONLY"
                    if winners.get(key) is item
                    else "BETTER_PRICE_AVAILABLE"
                )
            else:
                reason = str(item["reason"])

            selected = item["selected"]
            companion = item["companion"]
            evidence = _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "model_version": estimate.model.model_version,
                    "policy_version": self._policy.version,
                    "selected_observation_id": selected["market_observation_id"],
                    "companion_observation_id": companion["market_observation_id"],
                    "selection": item["selection"],
                    "lambda_home": estimate.expected_home_goals,
                    "lambda_away": estimate.expected_away_goals,
                }
            )
            decision = GoalDecision(
                decision_id="quantlab-goal-decision-v1:"
                + _fingerprint(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "evidence": evidence,
                        "reason": reason,
                    }
                ),
                fixture_id=str(fixture["fixture_id"]),
                decision_at=now,
                policy_version=self._policy.version,
                model_name=MODEL_NAME,
                model_version=estimate.model.model_version,
                bookmaker_id=int(pair["bookmaker_id"]),
                bookmaker_name=str(pair["bookmaker_name"]),
                provider_bet_id=int(pair["provider_bet_id"]),
                provider_bet_name=str(pair["provider_bet_name"]),
                market_key=str(pair["market_key"]),
                selection=str(item["selection"]),
                line=line,
                selected_observation_id=str(selected["market_observation_id"]),
                companion_observation_id=str(companion["market_observation_id"]),
                quote_observed_at=_utc(pair["captured_at"], "captured_at"),
                odds=float(item["odds"]),
                companion_odds=float(item["companion_odds"]),
                market_probability=float(item["market_probability"]),
                model_probability=float(item["model_probability"]),
                edge=float(item["edge"]),
                expected_value=float(item["expected_value"]),
                decision="PASS",
                reason=reason,
                evidence_fingerprint=evidence,
                details={
                    "expected_home_goals": estimate.expected_home_goals,
                    "expected_away_goals": estimate.expected_away_goals,
                    "rho": estimate.model.rho,
                    "feature_version": estimate.model.feature_version,
                    "training_sample_size": estimate.model.training_sample_size,
                    "history_match_count": estimate.model.history_match_count,
                    "home_history_size": estimate.snapshot.home_history_size,
                    "away_history_size": estimate.snapshot.away_history_size,
                    "companion_selection": item["companion_selection"],
                    "quote_age_seconds": item["quote_age_seconds"],
                    "seconds_to_kickoff": item["seconds_to_kickoff"],
                    "shadow_pick_authority": False,
                    "authority_gate": "HOLDOUT_AND_LEAKAGE_AUDIT_REQUIRED",
                    "bookmaker_features_used": False,
                    "provider_predictions_used": False,
                },
            )
            inserted += int(bool(self._repository.save_goal_decision(decision)))

        return GoalEngineResult(decisions_inserted=inserted, picks_inserted=0)
