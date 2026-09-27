"""CardLab single-book 1xBet shadow pick engine."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from h2h.quantlab.card_lab.model import (
    MODEL_NAME,
    MODEL_VERSION,
    total_cards_probability,
)
from h2h.quantlab.card_lab.settlement_contract import (
    API_FOOTBALL_CARDS_OVER_UNDER_BET_ID,
    card_settlement_contract_status,
)
from h2h.quantlab.reference_shadow_engine import (
    ContextMarketDecision,
    ReferenceEngineResult,
)
from h2h.quantlab.scope import card_corner_scope


POLICY_VERSION = "CARDLAB_1XBET_POISSON_POLICY_V5_MARKET80"
MARKET_KEY = "TOTAL_CARDS"
BOOKMAKER_ID = 11
PROVIDER_BET_ID = API_FOOTBALL_CARDS_OVER_UNDER_BET_ID
MIN_EDGE = 0.03
MIN_EXPECTED_VALUE = 0.03
MIN_ODDS = 1.40
MAX_ODDS = 4.00
MAX_QUOTE_AGE_SECONDS = 13 * 60 * 60
MIN_SECONDS_TO_KICKOFF = 15 * 60
MIN_REFEREE_SAMPLE_SIZE = 5
FLAT_STAKE_MINOR = 10_000


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


def _fair_probability(selected_odds: float, companion_odds: float) -> float:
    raw_selected = 1.0 / selected_odds
    raw_companion = 1.0 / companion_odds
    return raw_selected / (raw_selected + raw_companion)


def _supported_market(pair: dict[str, Any]) -> bool:
    if int(pair.get("bookmaker_id") or 0) != BOOKMAKER_ID:
        return False
    if int(pair.get("provider_bet_id") or 0) != PROVIDER_BET_ID:
        return False
    tokens = _tokens(pair.get("provider_bet_name"))
    if not ({"card", "cards"} & tokens):
        return False
    if tokens & {
        "yellow",
        "red",
        "booking",
        "bookings",
        "points",
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
    }:
        return False
    return _is_half_line(float(pair["line"]))


class CardLabShadowPickEngine:
    """Evaluate only 1xBet Cards Over/Under against CardLab's own probability model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

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
        details: dict[str, Any] | None = None,
    ) -> ReferenceEngineResult:
        evidence = _fingerprint(
            {
                "fixture_id": fixture["fixture_id"],
                "lab": "CARD",
                "policy_version": POLICY_VERSION,
                "reason": reason,
                "details": details or {},
            }
        )
        decision = ContextMarketDecision(
            decision_id="quantlab-context-decision-v1:"
            + _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "lab": "CARD",
                    "evidence": evidence,
                    "reason": reason,
                }
            ),
            fixture_id=str(fixture["fixture_id"]),
            lab="CARD",
            decision_at=now,
            policy_version=POLICY_VERSION,
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
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
            details=dict(details or {}),
        )
        inserted = self._repository.save_context_market_decision(decision)
        return ReferenceEngineResult(decisions_inserted=int(bool(inserted)))

    def run_fixture(
        self,
        fixture: dict[str, Any],
        *,
        decision_at: datetime,
    ) -> ReferenceEngineResult:
        now = _utc(decision_at, "decision_at")
        kickoff = _utc(fixture["kickoff_at"], "kickoff_at")
        if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
            return self._fixture_pass(
                fixture,
                now,
                reason="OUTSIDE_CARD_CORNER_SCOPE",
            )

        card_context = self._repository.latest_card_feature_snapshot(
            str(fixture["fixture_id"]),
            decision_at=now,
        )
        if card_context is None:
            return self._fixture_pass(
                fixture,
                now,
                reason="NO_CARD_FEATURE_SNAPSHOT",
            )
        referee_card_rate = card_context.get("referee_card_rate")
        referee_sample_size = int(card_context.get("referee_sample_size") or 0)
        if referee_card_rate is None or referee_sample_size < MIN_REFEREE_SAMPLE_SIZE:
            return self._fixture_pass(
                fixture,
                now,
                reason="INSUFFICIENT_REFEREE_HISTORY",
                details={
                    "referee_card_rate": referee_card_rate,
                    "referee_sample_size": referee_sample_size,
                    "minimum_sample_size": MIN_REFEREE_SAMPLE_SIZE,
                },
            )
        expected_total_cards = float(referee_card_rate)
        if not isfinite(expected_total_cards) or expected_total_cards <= 0:
            return self._fixture_pass(
                fixture,
                now,
                reason="INVALID_REFEREE_CARD_RATE",
                details={"referee_card_rate": referee_card_rate},
            )

        pairs = tuple(
            pair
            for pair in self._repository.total_market_pairs(
                str(fixture["fixture_id"]),
                lab_owner="CARD",
                decision_at=now,
            )
            if _supported_market(pair)
        )
        if not pairs:
            return self._fixture_pass(
                fixture,
                now,
                reason="NO_1XBET_CARDS_OVER_UNDER_MARKET",
            )

        evaluated: list[dict[str, Any]] = []
        for target in pairs:
            settlement_contract = card_settlement_contract_status(
                provider_bet_id=int(target["provider_bet_id"]),
                provider_bet_name=str(target["provider_bet_name"]),
                bookmaker_id=int(target["bookmaker_id"]),
            ).payload()
            if not bool(settlement_contract["supported"]):
                continue

            line = float(target["line"])
            target_capture = _utc(target["captured_at"], "captured_at")
            quote_age = (now - target_capture).total_seconds()
            seconds_to_kickoff = (kickoff - now).total_seconds()
            for selection, companion_selection in (("OVER", "UNDER"), ("UNDER", "OVER")):
                selected = target["selections"][selection]
                companion = target["selections"][companion_selection]
                odds = float(selected["odds"])
                companion_odds = float(companion["odds"])
                market_probability = _fair_probability(odds, companion_odds)
                model_probability = total_cards_probability(
                    referee_card_rate=expected_total_cards,
                    selection=selection,
                    line=line,
                )
                edge = model_probability - market_probability
                expected_value = model_probability * odds - 1.0

                reason: str | None = None
                if seconds_to_kickoff < MIN_SECONDS_TO_KICKOFF:
                    reason = "KICKOFF_TOO_CLOSE"
                elif quote_age < 0:
                    reason = "QUOTE_FROM_FUTURE"
                elif quote_age > MAX_QUOTE_AGE_SECONDS:
                    reason = "STALE_QUOTE"
                elif not MIN_ODDS <= odds <= MAX_ODDS:
                    reason = "ODDS_OUTSIDE_RANGE"
                elif edge < MIN_EDGE:
                    reason = "EDGE_BELOW_MINIMUM"
                elif expected_value < MIN_EXPECTED_VALUE:
                    reason = "EV_BELOW_MINIMUM"

                evaluated.append(
                    {
                        "target": target,
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
                        "settlement_contract": settlement_contract,
                        "reason": reason,
                    }
                )

        if not evaluated:
            return self._fixture_pass(
                fixture,
                now,
                reason="NO_CANONICAL_SETTLEMENT_CONTRACT",
            )

        winners: dict[float, dict[str, Any]] = {}
        for item in evaluated:
            if item["reason"] is not None:
                continue
            line = float(item["target"]["line"])
            current = winners.get(line)
            score = (
                float(item["expected_value"]),
                float(item["edge"]),
                float(item["odds"]),
                1 if item["selection"] == "OVER" else 0,
            )
            if current is None:
                winners[line] = item
                continue
            current_score = (
                float(current["expected_value"]),
                float(current["edge"]),
                float(current["odds"]),
                1 if current["selection"] == "OVER" else 0,
            )
            if score > current_score:
                winners[line] = item

        decisions_inserted = 0
        picks_inserted = 0
        for item in evaluated:
            target = item["target"]
            line = float(target["line"])
            if item["reason"] is None:
                if winners.get(line) is item:
                    decision_value, reason = "PICK", "VALUE_THRESHOLD_PASSED"
                else:
                    decision_value, reason = "PASS", "BETTER_VALUE_AVAILABLE"
            else:
                decision_value, reason = "PASS", str(item["reason"])

            selected = item["selected"]
            companion = item["companion"]
            evidence = _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "lab": "CARD",
                    "policy_version": POLICY_VERSION,
                    "model_version": MODEL_VERSION,
                    "target": [
                        selected["market_observation_id"],
                        companion["market_observation_id"],
                    ],
                    "referee_card_rate": expected_total_cards,
                    "referee_sample_size": referee_sample_size,
                }
            )
            decision = ContextMarketDecision(
                decision_id="quantlab-context-decision-v1:"
                + _fingerprint(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "lab": "CARD",
                        "evidence": evidence,
                        "selected_observation_id": selected["market_observation_id"],
                        "decision": decision_value,
                        "reason": reason,
                    }
                ),
                fixture_id=str(fixture["fixture_id"]),
                lab="CARD",
                decision_at=now,
                policy_version=POLICY_VERSION,
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                bookmaker_id=BOOKMAKER_ID,
                bookmaker_name=str(target["bookmaker_name"]),
                reference_bookmaker_id=None,
                reference_bookmaker_name=None,
                provider_bet_id=PROVIDER_BET_ID,
                provider_bet_name=str(target["provider_bet_name"]),
                market_key=MARKET_KEY,
                selection=str(item["selection"]),
                line=line,
                selected_observation_id=str(selected["market_observation_id"]),
                companion_observation_id=str(companion["market_observation_id"]),
                reference_observation_id=None,
                reference_companion_observation_id=None,
                quote_observed_at=_utc(target["captured_at"], "captured_at"),
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
                    "companion_selection": item["companion_selection"],
                    "target_quote_age_seconds": item["quote_age_seconds"],
                    "seconds_to_kickoff": item["seconds_to_kickoff"],
                    "card_context": card_context,
                    "expected_total_cards": expected_total_cards,
                    "probability_model": {
                        "name": MODEL_NAME,
                        "version": MODEL_VERSION,
                        "distribution": "Poisson",
                        "lambda_source": "referee_card_rate",
                        "reference_bookmaker_used": False,
                    },
                    "settlement_contract": item["settlement_contract"],
                    "thresholds": {
                        "min_edge": MIN_EDGE,
                        "min_expected_value": MIN_EXPECTED_VALUE,
                        "min_odds": MIN_ODDS,
                        "max_odds": MAX_ODDS,
                        "max_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
                        "min_seconds_to_kickoff": MIN_SECONDS_TO_KICKOFF,
                        "min_referee_sample_size": MIN_REFEREE_SAMPLE_SIZE,
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
