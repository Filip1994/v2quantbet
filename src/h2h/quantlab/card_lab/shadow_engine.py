"""CardLab 1xBet shadow picks driven by raw pre-match statistics only."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from h2h.quantlab.card_lab.settlement_contract import (
    API_FOOTBALL_CARDS_OVER_UNDER_BET_ID,
    card_settlement_contract_status,
)
from h2h.quantlab.reference_shadow_engine import ContextMarketDecision, ReferenceEngineResult
from h2h.quantlab.scope import card_corner_scope


POLICY_VERSION = "CARDLAB_RAW_STATS_POLICY_V7_REFEREE_WEB"
MODEL_NAME = "CardLab raw-stat consensus"
MODEL_VERSION = "CARDLAB_RAW_STATS_V2"
MARKET_KEY = "TOTAL_CARDS"
BOOKMAKER_ID = 11
PROVIDER_BET_ID = API_FOOTBALL_CARDS_OVER_UNDER_BET_ID

MAX_QUOTE_AGE_SECONDS = 13 * 60 * 60
MIN_SECONDS_TO_KICKOFF = 15 * 60
MIN_RAW_ANCHORS = 3
MIN_DIRECTIONAL_SUPPORT = 0.60
MIN_ABS_LINE_GAP = 0.35
MIN_OBSERVED_HIT_RATE = 0.50
MIN_REFEREE_WEB_MATCHES = 10
FLAT_STAKE_MINOR = 10_000


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


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


def _raw_line_signal(card_context: dict[str, Any], line: float) -> dict[str, Any] | None:
    payload = card_context.get("feature_payload")
    if not isinstance(payload, dict):
        return None
    raw_features = payload.get("raw_features")
    raw_anchors = payload.get("raw_anchors")
    raw_anchor_weights = payload.get("raw_anchor_weights")
    raw_samples = payload.get("raw_samples")
    raw_sample_weights = payload.get("raw_sample_weights")
    if not isinstance(raw_features, dict) or not isinstance(raw_anchors, dict):
        return None
    anchors = {
        str(key): number
        for key, value in raw_anchors.items()
        if (number := _number(value)) is not None
    }
    if len(anchors) < MIN_RAW_ANCHORS:
        return None

    weights = {
        key: max(
            0.0,
            _number(raw_anchor_weights.get(key)) or 1.0,
        )
        if isinstance(raw_anchor_weights, dict)
        else 1.0
        for key in anchors
    }
    if sum(weights.values()) <= 0:
        weights = {key: 1.0 for key in anchors}
    ordered = sorted((value, weights[key]) for key, value in anchors.items())
    half_weight = sum(weight for _, weight in ordered) / 2.0
    cumulative = 0.0
    consensus = ordered[-1][0]
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= half_weight:
            consensus = value
            break

    if abs(consensus - line) <= 1e-9:
        return None
    selection = "OVER" if consensus > line else "UNDER"
    directional_support = sum(
        weights[key]
        for key, value in anchors.items()
        if (value > line if selection == "OVER" else value < line)
    ) / sum(weights.values())

    weighted_rates: list[tuple[float, float]] = []
    sample_sizes: dict[str, int] = {}
    if isinstance(raw_samples, dict):
        for key, values in raw_samples.items():
            if not isinstance(values, list):
                continue
            clean = [number for value in values if (number := _number(value)) is not None]
            if not clean:
                continue
            hits = sum(
                (value > line if selection == "OVER" else value < line)
                for value in clean
            )
            sample_weight = (
                max(0.0, _number(raw_sample_weights.get(key)) or 1.0)
                if isinstance(raw_sample_weights, dict)
                else 1.0
            )
            weighted_rates.append((hits / len(clean), sample_weight))
            sample_sizes[str(key)] = len(clean)
    total_rate_weight = sum(weight for _, weight in weighted_rates)
    observed_hit_rate = (
        None
        if not weighted_rates or total_rate_weight <= 0
        else sum(rate * weight for rate, weight in weighted_rates) / total_rate_weight
    )
    gap = consensus - line

    reason: str | None = None
    if abs(gap) < MIN_ABS_LINE_GAP:
        reason = "RAW_LINE_GAP_TOO_SMALL"
    elif directional_support < MIN_DIRECTIONAL_SUPPORT:
        reason = "RAW_DIRECTION_SUPPORT_TOO_LOW"
    elif observed_hit_rate is not None and observed_hit_rate < MIN_OBSERVED_HIT_RATE:
        reason = "RAW_HISTORICAL_HIT_RATE_TOO_LOW"

    support_probability = directional_support
    if observed_hit_rate is not None:
        support_probability = (directional_support + observed_hit_rate) / 2.0
    support_probability = min(0.999999, max(0.000001, support_probability))
    strength = abs(gap) * directional_support * (
        1.0 if observed_hit_rate is None else (0.75 + 0.25 * observed_hit_rate)
    )

    return {
        "selection": selection,
        "line": line,
        "consensus_cards": consensus,
        "line_gap": gap,
        "anchor_count": len(anchors),
        "anchors": anchors,
        "anchor_weights": weights,
        "directional_support": directional_support,
        "observed_hit_rate": observed_hit_rate,
        "sample_sizes": sample_sizes,
        "support_probability": support_probability,
        "strength": strength,
        "reason": reason,
        "raw_features": raw_features,
    }


class CardLabShadowPickEngine:
    """Choose one CardLab exposure per fixture from raw-statistical consensus."""

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
            return self._fixture_pass(fixture, now, reason="OUTSIDE_CARD_CORNER_SCOPE")

        card_context = self._repository.latest_card_feature_snapshot(
            str(fixture["fixture_id"]),
            decision_at=now,
        )
        if card_context is None:
            return self._fixture_pass(fixture, now, reason="NO_CARD_FEATURE_SNAPSHOT")

        if card_context.get("feature_version") != "CARDLAB_FEATURES_V4":
            return self._fixture_pass(
                fixture,
                now,
                reason="REFEREE_WEB_FEATURES_REQUIRED",
                details={"required_feature_version": "CARDLAB_FEATURES_V4"},
            )
        payload = card_context.get("feature_payload")
        raw_features = payload.get("raw_features") if isinstance(payload, dict) else None
        if not isinstance(raw_features, dict):
            return self._fixture_pass(fixture, now, reason="NO_CARD_RAW_FEATURES")
        if int(raw_features.get("web_referee_supported_league") or 0) != 1:
            return self._fixture_pass(
                fixture,
                now,
                reason="UNSUPPORTED_REFEREE_WEB_LEAGUE",
                details={
                    "supported_leagues": "Premier League, La Liga, Serie A, Bundesliga, Ligue 1"
                },
            )
        web_matches = int(raw_features.get("web_referee_matches") or 0)
        if web_matches < MIN_REFEREE_WEB_MATCHES:
            return self._fixture_pass(
                fixture,
                now,
                reason="INSUFFICIENT_REFEREE_WEB_HISTORY",
                details={
                    "web_referee_matches": web_matches,
                    "minimum_web_referee_matches": MIN_REFEREE_WEB_MATCHES,
                    "web_referee_league_key": raw_features.get("web_referee_league_key"),
                },
            )
        raw_anchors = payload.get("raw_anchors") if isinstance(payload, dict) else None
        if not isinstance(raw_anchors, dict) or len(raw_anchors) < MIN_RAW_ANCHORS:
            return self._fixture_pass(
                fixture,
                now,
                reason="INSUFFICIENT_RAW_STAT_HISTORY",
                details={
                    "raw_anchor_count": 0 if not isinstance(raw_anchors, dict) else len(raw_anchors),
                    "minimum_raw_anchors": MIN_RAW_ANCHORS,
                },
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
        seconds_to_kickoff = (kickoff - now).total_seconds()
        for target in pairs:
            settlement_contract = card_settlement_contract_status(
                provider_bet_id=int(target["provider_bet_id"]),
                provider_bet_name=str(target["provider_bet_name"]),
                bookmaker_id=int(target["bookmaker_id"]),
            ).payload()
            if not bool(settlement_contract["supported"]):
                continue

            line = float(target["line"])
            signal = _raw_line_signal(card_context, line)
            if signal is None:
                continue
            selection = str(signal["selection"])
            companion_selection = "UNDER" if selection == "OVER" else "OVER"
            selected = target["selections"][selection]
            companion = target["selections"][companion_selection]
            odds = float(selected["odds"])
            companion_odds = float(companion["odds"])
            target_capture = _utc(target["captured_at"], "captured_at")
            quote_age = (now - target_capture).total_seconds()

            reason = signal.get("reason")
            if seconds_to_kickoff < MIN_SECONDS_TO_KICKOFF:
                reason = "KICKOFF_TOO_CLOSE"
            elif quote_age < 0:
                reason = "QUOTE_FROM_FUTURE"
            elif quote_age > MAX_QUOTE_AGE_SECONDS:
                reason = "STALE_QUOTE"

            market_probability = _fair_probability(odds, companion_odds)
            support_probability = float(signal["support_probability"])
            # These remain compatibility/diagnostic ledger fields only. They never gate PICK.
            edge = support_probability - market_probability
            expected_value = support_probability * odds - 1.0

            evaluated.append(
                {
                    "target": target,
                    "signal": signal,
                    "selection": selection,
                    "companion_selection": companion_selection,
                    "selected": selected,
                    "companion": companion,
                    "odds": odds,
                    "companion_odds": companion_odds,
                    "market_probability": market_probability,
                    "model_probability": support_probability,
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
                reason="NO_RAW_STAT_LINE_SIGNAL",
                details={"minimum_raw_anchors": MIN_RAW_ANCHORS},
            )

        eligible = [item for item in evaluated if item["reason"] is None]
        canonical = (
            max(
                eligible,
                key=lambda item: (
                    float(item["signal"]["strength"]),
                    float(item["signal"]["directional_support"]),
                    abs(float(item["signal"]["line_gap"])),
                    -float(item["target"]["line"]),
                ),
            )
            if eligible
            else None
        )

        decisions_inserted = 0
        picks_inserted = 0
        for item in evaluated:
            if item["reason"] is not None:
                decision_value, reason = "PASS", str(item["reason"])
            elif item is canonical:
                decision_value, reason = "PICK", "RAW_STAT_CONSENSUS_PICK"
            else:
                decision_value, reason = "PASS", "STRONGER_RAW_STAT_LINE_AVAILABLE"

            target = item["target"]
            selected = item["selected"]
            companion = item["companion"]
            signal = item["signal"]
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
                    "raw_signal": {
                        key: signal[key]
                        for key in (
                            "selection",
                            "line",
                            "consensus_cards",
                            "line_gap",
                            "anchor_count",
                            "directional_support",
                            "observed_hit_rate",
                            "strength",
                        )
                    },
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
                line=float(target["line"]),
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
                    "card_context": card_context,
                    "raw_signal": signal,
                    "raw_stat_policy": {
                        "price_independent_selection": True,
                        "ev_is_pick_gate": False,
                        "edge_is_pick_gate": False,
                        "odds_is_pick_gate": False,
                        "one_pick_per_fixture": True,
                        "referee_web_top_league_gate": True,
                        "minimum_referee_web_matches": MIN_REFEREE_WEB_MATCHES,
                    },
                    "price_diagnostics": {
                        "market_probability": item["market_probability"],
                        "raw_support_probability": item["model_probability"],
                        "edge": item["edge"],
                        "expected_value": item["expected_value"],
                        "used_for_selection": False,
                    },
                    "settlement_contract": item["settlement_contract"],
                    "thresholds": {
                        "minimum_raw_anchors": MIN_RAW_ANCHORS,
                        "minimum_directional_support": MIN_DIRECTIONAL_SUPPORT,
                        "minimum_abs_line_gap": MIN_ABS_LINE_GAP,
                        "minimum_observed_hit_rate": MIN_OBSERVED_HIT_RATE,
                        "minimum_referee_web_matches": MIN_REFEREE_WEB_MATCHES,
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
