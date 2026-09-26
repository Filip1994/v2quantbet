"""CornerLab V2 structural pressure-model shadow pick engine."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from h2h.quantlab.corner_lab.model import MODEL_NAME, CornerPressureModelService
from h2h.quantlab.reference_shadow_engine import ContextMarketDecision, ReferenceEngineResult


POLICY_VERSION = "CORNERLAB_PRESSURE_POISSON_POLICY_V2"
MARKET_KEY = "TOTAL_CORNERS"
MIN_EDGE = 0.03
MIN_EXPECTED_VALUE = 0.03
MIN_ODDS = 1.40
MAX_ODDS = 4.00
MAX_QUOTE_AGE_SECONDS = 13 * 60 * 60
MIN_SECONDS_TO_KICKOFF = 15 * 60
FLAT_STAKE_MINOR = 10_000

_BLOCKED = frozenset(
    {
        "half",
        "1st",
        "2nd",
        "first",
        "second",
        "home",
        "away",
        "team",
        "handicap",
        "race",
        "range",
        "exact",
        "odd",
        "even",
        "asian",
    }
)


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


def _tokens(value: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _is_half_line(line: float) -> bool:
    doubled = line * 2.0
    nearest = round(doubled)
    return abs(doubled - nearest) <= 1e-9 and int(nearest) % 2 == 1


def _market_name_supported(provider_bet_name: str) -> bool:
    tokens = _tokens(provider_bet_name)
    return bool({"corner", "corners"} & tokens) and not bool(tokens & _BLOCKED)


def _fair_probability(selected_odds: float, companion_odds: float) -> float:
    selected = 1.0 / selected_odds
    companion = 1.0 / companion_odds
    return selected / (selected + companion)


class CornerLabShadowPickEngine:
    """Use structural corner pressure probabilities; bookmaker price is only the benchmark."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository
        self._model = CornerPressureModelService(repository)

    def _fixture_pass(
        self,
        fixture: dict[str, Any],
        now: datetime,
        *,
        reason: str,
        model_version: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> ReferenceEngineResult:
        payload = details or {}
        evidence = _fingerprint(
            {
                "fixture_id": fixture["fixture_id"],
                "policy_version": POLICY_VERSION,
                "reason": reason,
                "model_version": model_version,
                "details": payload,
            }
        )
        decision = ContextMarketDecision(
            decision_id="quantlab-context-decision-v1:"
            + _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "lab": "CORNER",
                    "evidence": evidence,
                }
            ),
            fixture_id=str(fixture["fixture_id"]),
            lab="CORNER",
            decision_at=now,
            policy_version=POLICY_VERSION,
            model_name=MODEL_NAME,
            model_version=model_version,
            bookmaker_id=None,
            bookmaker_name=None,
            reference_bookmaker_id=None,
            reference_bookmaker_name=None,
            provider_bet_id=None,
            provider_bet_name=None,
            market_key=None,
            selection=None,
            line=None,
            selected_observation_id=None,
            companion_observation_id=None,
            reference_observation_id=None,
            reference_companion_observation_id=None,
            quote_observed_at=None,
            reference_quote_observed_at=None,
            odds=None,
            companion_odds=None,
            reference_odds=None,
            reference_companion_odds=None,
            market_probability=None,
            model_probability=None,
            edge=None,
            expected_value=None,
            decision="PASS",
            reason=reason,
            evidence_fingerprint=evidence,
            details=dict(payload),
        )
        return ReferenceEngineResult(
            decisions_inserted=int(bool(self._repository.save_context_market_decision(decision)))
        )

    def run_fixture(
        self,
        fixture: dict[str, Any],
        *,
        decision_at: datetime,
    ) -> ReferenceEngineResult:
        now = _utc(decision_at, "decision_at")
        kickoff = _utc(fixture["kickoff_at"], "kickoff_at")

        model_result = self._model.estimate(fixture, decision_at=now)
        if model_result.estimate is None:
            return self._fixture_pass(
                fixture,
                now,
                reason=model_result.reason,
                details=model_result.details,
            )
        estimate = model_result.estimate

        pairs = tuple(
            pair
            for pair in self._repository.total_market_pairs(
                str(fixture["fixture_id"]),
                lab_owner="CORNER",
                decision_at=now,
            )
            if _market_name_supported(str(pair["provider_bet_name"]))
            and _is_half_line(float(pair["line"]))
        )
        if not pairs:
            return self._fixture_pass(
                fixture,
                now,
                reason="NO_SUPPORTED_TOTAL_MARKET",
                model_version=estimate.model.model_version,
                details={
                    "expected_total_corners": estimate.expected_total_corners,
                    **model_result.details,
                },
            )

        evaluated: list[dict[str, Any]] = []
        for pair in pairs:
            for selection, companion_selection in (("OVER", "UNDER"), ("UNDER", "OVER")):
                selected = pair["selections"][selection]
                companion = pair["selections"][companion_selection]
                odds = float(selected["odds"])
                companion_odds = float(companion["odds"])
                line = float(pair["line"])
                market_probability = _fair_probability(odds, companion_odds)
                model_probability = estimate.probability(selection, line)
                edge = model_probability - market_probability
                expected_value = model_probability * odds - 1.0
                captured_at = _utc(pair["captured_at"], "captured_at")
                quote_age = (now - captured_at).total_seconds()
                seconds_to_kickoff = (kickoff - now).total_seconds()

                reason: str | None = None
                if seconds_to_kickoff < MIN_SECONDS_TO_KICKOFF:
                    reason = "KICKOFF_TOO_CLOSE"
                elif quote_age < 0:
                    reason = "QUOTE_FROM_FUTURE"
                elif quote_age > MAX_QUOTE_AGE_SECONDS:
                    reason = "STALE_QUOTE"
                elif not MIN_ODDS <= odds <= MAX_ODDS:
                    reason = "ODDS_OUTSIDE_RANGE"
                elif not isfinite(model_probability) or not 0 < model_probability < 1:
                    reason = "INVALID_CORNER_MODEL_OUTPUT"
                elif edge < MIN_EDGE:
                    reason = "EDGE_BELOW_MINIMUM"
                elif expected_value < MIN_EXPECTED_VALUE:
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
                        "line": line,
                        "market_probability": market_probability,
                        "model_probability": model_probability,
                        "edge": edge,
                        "expected_value": expected_value,
                        "quote_age_seconds": quote_age,
                        "seconds_to_kickoff": seconds_to_kickoff,
                        "reason": reason,
                    }
                )

        winners: dict[float, dict[str, Any]] = {}
        for item in evaluated:
            if item["reason"] is not None:
                continue
            line = float(item["line"])
            current = winners.get(line)
            score = (
                float(item["expected_value"]),
                float(item["edge"]),
                float(item["odds"]),
                -int(item["pair"]["bookmaker_id"]),
                1 if item["selection"] == "OVER" else 0,
            )
            if current is None:
                winners[line] = item
                continue
            current_score = (
                float(current["expected_value"]),
                float(current["edge"]),
                float(current["odds"]),
                -int(current["pair"]["bookmaker_id"]),
                1 if current["selection"] == "OVER" else 0,
            )
            if score > current_score:
                winners[line] = item

        decisions_inserted = 0
        picks_inserted = 0
        for item in evaluated:
            pair = item["pair"]
            selected = item["selected"]
            companion = item["companion"]
            line = float(item["line"])
            if item["reason"] is None:
                if winners.get(line) is item:
                    decision_value, reason = "PICK", "VALUE_THRESHOLD_PASSED"
                else:
                    decision_value, reason = "PASS", "BETTER_VALUE_AVAILABLE"
            else:
                decision_value, reason = "PASS", str(item["reason"])

            evidence = _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "policy_version": POLICY_VERSION,
                    "model_version": estimate.model.model_version,
                    "selected_observation_id": selected["market_observation_id"],
                    "companion_observation_id": companion["market_observation_id"],
                    "selection": item["selection"],
                    "expected_total_corners": estimate.expected_total_corners,
                }
            )
            decision = ContextMarketDecision(
                decision_id="quantlab-context-decision-v1:"
                + _fingerprint(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "lab": "CORNER",
                        "evidence": evidence,
                        "decision": decision_value,
                        "reason": reason,
                    }
                ),
                fixture_id=str(fixture["fixture_id"]),
                lab="CORNER",
                decision_at=now,
                policy_version=POLICY_VERSION,
                model_name=MODEL_NAME,
                model_version=estimate.model.model_version,
                bookmaker_id=int(pair["bookmaker_id"]),
                bookmaker_name=str(pair["bookmaker_name"]),
                reference_bookmaker_id=None,
                reference_bookmaker_name=None,
                provider_bet_id=int(pair["provider_bet_id"]),
                provider_bet_name=str(pair["provider_bet_name"]),
                market_key=MARKET_KEY,
                selection=str(item["selection"]),
                line=line,
                selected_observation_id=str(selected["market_observation_id"]),
                companion_observation_id=str(companion["market_observation_id"]),
                reference_observation_id=None,
                reference_companion_observation_id=None,
                quote_observed_at=_utc(pair["captured_at"], "captured_at"),
                reference_quote_observed_at=None,
                odds=float(item["odds"]),
                companion_odds=float(item["companion_odds"]),
                reference_odds=None,
                reference_companion_odds=None,
                market_probability=float(item["market_probability"]),
                model_probability=float(item["model_probability"]),
                edge=float(item["edge"]),
                expected_value=float(item["expected_value"]),
                decision=decision_value,
                reason=reason,
                evidence_fingerprint=evidence,
                details={
                    "expected_total_corners": estimate.expected_total_corners,
                    "feature_version": estimate.model.feature_version,
                    "training_sample_size": estimate.model.training_sample_size,
                    "history_match_count": estimate.model.history_match_count,
                    "home_history_size": estimate.snapshot.home_history_size,
                    "away_history_size": estimate.snapshot.away_history_size,
                    "companion_selection": item["companion_selection"],
                    "quote_age_seconds": item["quote_age_seconds"],
                    "seconds_to_kickoff": item["seconds_to_kickoff"],
                    "cross_book_reference_used": False,
                    "thresholds": {
                        "min_edge": MIN_EDGE,
                        "min_expected_value": MIN_EXPECTED_VALUE,
                        "min_odds": MIN_ODDS,
                        "max_odds": MAX_ODDS,
                        "max_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
                        "min_seconds_to_kickoff": MIN_SECONDS_TO_KICKOFF,
                    },
                },
            )
            inserted = bool(self._repository.save_context_market_decision(decision))
            decisions_inserted += int(inserted)
            if decision_value == "PICK" and inserted:
                picks_inserted += int(
                    bool(
                        self._repository.save_context_shadow_bet(
                            decision,
                            stake_minor=FLAT_STAKE_MINOR,
                        )
                    )
                )

        return ReferenceEngineResult(
            decisions_inserted=decisions_inserted,
            picks_inserted=picks_inserted,
        )
