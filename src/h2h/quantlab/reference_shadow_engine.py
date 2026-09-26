"""Shared shadow-only value engine for CornerLab and CardLab total markets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from h2h.quantlab.scope import card_corner_scope


@dataclass(frozen=True, slots=True)
class ReferenceShadowPolicy:
    lab: str
    market_key: str
    policy_version: str
    model_name: str
    model_version: str
    min_edge: float = 0.03
    min_expected_value: float = 0.03
    min_odds: float = 1.40
    max_odds: float = 4.00
    max_quote_age_seconds: int = 13 * 60 * 60
    min_seconds_to_kickoff: int = 15 * 60
    flat_stake_minor: int = 10_000
    min_referee_sample_size: int = 5

    def __post_init__(self) -> None:
        if self.lab not in {"CORNER", "CARD"}:
            raise ValueError("lab must be CORNER or CARD")
        for name in ("market_key", "policy_version", "model_name", "model_version"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be blank")
        for name in ("min_edge", "min_expected_value"):
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not 1.0 < self.min_odds <= self.max_odds:
            raise ValueError("odds bounds must satisfy 1 < min_odds <= max_odds")
        for name in (
            "max_quote_age_seconds",
            "min_seconds_to_kickoff",
            "flat_stake_minor",
            "min_referee_sample_size",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ContextMarketDecision:
    decision_id: str
    fixture_id: str
    lab: str
    decision_at: datetime
    policy_version: str
    model_name: str | None
    model_version: str | None
    bookmaker_id: int | None
    bookmaker_name: str | None
    reference_bookmaker_id: int | None
    reference_bookmaker_name: str | None
    provider_bet_id: int | None
    provider_bet_name: str | None
    market_key: str | None
    selection: str | None
    line: float | None
    selected_observation_id: str | None
    companion_observation_id: str | None
    reference_observation_id: str | None
    reference_companion_observation_id: str | None
    quote_observed_at: datetime | None
    reference_quote_observed_at: datetime | None
    odds: float | None
    companion_odds: float | None
    reference_odds: float | None
    reference_companion_odds: float | None
    market_probability: float | None
    model_probability: float | None
    edge: float | None
    expected_value: float | None
    decision: str
    reason: str
    evidence_fingerprint: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReferenceEngineResult:
    decisions_inserted: int = 0
    picks_inserted: int = 0


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


class ReferenceShadowPickEngine:
    """Evaluate persisted total-market quotes without provider calls or production writes."""

    _COMMON_BLOCKED = frozenset(
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

    def __init__(self, repository: Any, *, policy: ReferenceShadowPolicy) -> None:
        self._repository = repository
        self._policy = policy

    @staticmethod
    def _scope_kwargs(fixture: dict[str, Any]) -> dict[str, object]:
        return {
            "country": fixture.get("country"),
            "competition_name": fixture.get("competition_name"),
            "competition_type": fixture.get("competition_type"),
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
        }

    def _market_name_supported(self, provider_bet_name: str) -> bool:
        tokens = _tokens(provider_bet_name)
        if tokens & self._COMMON_BLOCKED:
            return False
        if self._policy.lab == "CORNER":
            if not ({"corner", "corners"} & tokens):
                return False
        else:
            if not ({"card", "cards"} & tokens):
                return False
            if tokens & {"yellow", "red", "booking", "bookings", "points"}:
                return False
        return True

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
                "lab": self._policy.lab,
                "policy_version": self._policy.policy_version,
                "reason": reason,
                "details": details or {},
            }
        )
        decision = ContextMarketDecision(
            decision_id="quantlab-context-decision-v1:"
            + _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "lab": self._policy.lab,
                    "evidence": evidence,
                    "reason": reason,
                }
            ),
            fixture_id=str(fixture["fixture_id"]),
            lab=self._policy.lab,
            decision_at=now,
            policy_version=self._policy.policy_version,
            model_name=self._policy.model_name,
            model_version=self._policy.model_version,
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

    def _card_context(
        self, fixture: dict[str, Any], now: datetime
    ) -> tuple[dict[str, Any] | None, ReferenceEngineResult | None]:
        if self._policy.lab != "CARD":
            return None, None
        snapshot = self._repository.latest_card_feature_snapshot(
            str(fixture["fixture_id"]), decision_at=now
        )
        if snapshot is None:
            return None, self._fixture_pass(
                fixture,
                now,
                reason="NO_CARD_FEATURE_SNAPSHOT",
            )
        card_rate = snapshot.get("referee_card_rate")
        sample_size = int(snapshot.get("referee_sample_size") or 0)
        if card_rate is None or sample_size < self._policy.min_referee_sample_size:
            return snapshot, self._fixture_pass(
                fixture,
                now,
                reason="INSUFFICIENT_REFEREE_HISTORY",
                details={
                    "referee_card_rate": card_rate,
                    "referee_sample_size": sample_size,
                    "minimum_sample_size": self._policy.min_referee_sample_size,
                },
            )
        return snapshot, None

    def run_fixture(
        self, fixture: dict[str, Any], *, decision_at: datetime
    ) -> ReferenceEngineResult:
        now = _utc(decision_at, "decision_at")
        kickoff = _utc(fixture["kickoff_at"], "kickoff_at")
        if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
            return self._fixture_pass(fixture, now, reason="OUTSIDE_CARD_CORNER_SCOPE")

        card_context, blocked = self._card_context(fixture, now)
        if blocked is not None:
            return blocked

        pairs = tuple(
            pair
            for pair in self._repository.total_market_pairs(
                str(fixture["fixture_id"]),
                lab_owner=self._policy.lab,
                decision_at=now,
            )
            if self._market_name_supported(str(pair["provider_bet_name"]))
            and _is_half_line(float(pair["line"]))
        )
        if not pairs:
            return self._fixture_pass(
                fixture,
                now,
                reason="NO_SUPPORTED_TOTAL_MARKET",
            )

        groups: dict[tuple[int, float], list[dict[str, Any]]] = {}
        for pair in pairs:
            key = (int(pair["provider_bet_id"]), float(pair["line"]))
            groups.setdefault(key, []).append(pair)
        cross_book = {
            key: rows
            for key, rows in groups.items()
            if len({int(row["bookmaker_id"]) for row in rows}) >= 2
        }
        if not cross_book:
            return self._fixture_pass(
                fixture,
                now,
                reason="NO_INDEPENDENT_REFERENCE_BOOK",
            )

        evaluated: list[dict[str, Any]] = []
        for rows in cross_book.values():
            for target in rows:
                references = [
                    row
                    for row in rows
                    if int(row["bookmaker_id"]) != int(target["bookmaker_id"])
                ]
                if not references:
                    continue
                reference = max(
                    references,
                    key=lambda row: (row["captured_at"], -int(row["bookmaker_id"])),
                )
                for selection, companion_selection in (("OVER", "UNDER"), ("UNDER", "OVER")):
                    selected = target["selections"][selection]
                    companion = target["selections"][companion_selection]
                    ref_selected = reference["selections"][selection]
                    ref_companion = reference["selections"][companion_selection]
                    odds = float(selected["odds"])
                    companion_odds = float(companion["odds"])
                    reference_odds = float(ref_selected["odds"])
                    reference_companion_odds = float(ref_companion["odds"])
                    market_probability = _fair_probability(odds, companion_odds)
                    model_probability = _fair_probability(
                        reference_odds, reference_companion_odds
                    )
                    edge = model_probability - market_probability
                    expected_value = model_probability * odds - 1.0
                    target_capture = _utc(target["captured_at"], "captured_at")
                    reference_capture = _utc(reference["captured_at"], "reference_captured_at")
                    target_age = (now - target_capture).total_seconds()
                    reference_age = (now - reference_capture).total_seconds()
                    seconds_to_kickoff = (kickoff - now).total_seconds()

                    reason: str | None = None
                    if seconds_to_kickoff < self._policy.min_seconds_to_kickoff:
                        reason = "KICKOFF_TOO_CLOSE"
                    elif target_age < 0 or reference_age < 0:
                        reason = "QUOTE_FROM_FUTURE"
                    elif max(target_age, reference_age) > self._policy.max_quote_age_seconds:
                        reason = "STALE_QUOTE"
                    elif not self._policy.min_odds <= odds <= self._policy.max_odds:
                        reason = "ODDS_OUTSIDE_RANGE"
                    elif self._policy.lab == "CARD":
                        referee_rate = float(card_context["referee_card_rate"])
                        line = float(target["line"])
                        if (selection == "OVER" and referee_rate <= line) or (
                            selection == "UNDER" and referee_rate >= line
                        ):
                            reason = "REFEREE_RATE_DIRECTION_DISAGREES"
                    if reason is None and edge < self._policy.min_edge:
                        reason = "EDGE_BELOW_MINIMUM"
                    if reason is None and expected_value < self._policy.min_expected_value:
                        reason = "EV_BELOW_MINIMUM"

                    evaluated.append(
                        {
                            "target": target,
                            "reference": reference,
                            "selection": selection,
                            "companion_selection": companion_selection,
                            "selected": selected,
                            "companion": companion,
                            "reference_selected": ref_selected,
                            "reference_companion": ref_companion,
                            "odds": odds,
                            "companion_odds": companion_odds,
                            "reference_odds": reference_odds,
                            "reference_companion_odds": reference_companion_odds,
                            "market_probability": market_probability,
                            "model_probability": model_probability,
                            "edge": edge,
                            "expected_value": expected_value,
                            "target_age_seconds": target_age,
                            "reference_age_seconds": reference_age,
                            "seconds_to_kickoff": seconds_to_kickoff,
                            "reason": reason,
                        }
                    )

        winners: dict[tuple[str, float], dict[str, Any]] = {}
        for item in evaluated:
            if item["reason"] is not None:
                continue
            target = item["target"]
            key = (self._policy.market_key, float(target["line"]))
            current = winners.get(key)
            score = (
                float(item["expected_value"]),
                float(item["edge"]),
                float(item["odds"]),
                -int(target["bookmaker_id"]),
                1 if item["selection"] == "OVER" else 0,
            )
            if current is None:
                winners[key] = item
                continue
            current_target = current["target"]
            current_score = (
                float(current["expected_value"]),
                float(current["edge"]),
                float(current["odds"]),
                -int(current_target["bookmaker_id"]),
                1 if current["selection"] == "OVER" else 0,
            )
            if score > current_score:
                winners[key] = item

        decisions_inserted = 0
        picks_inserted = 0
        for item in evaluated:
            target = item["target"]
            reference = item["reference"]
            line = float(target["line"])
            key = (self._policy.market_key, line)
            if item["reason"] is None:
                if winners.get(key) is item:
                    decision_value, reason = "PICK", "VALUE_THRESHOLD_PASSED"
                else:
                    decision_value, reason = "PASS", "BETTER_VALUE_AVAILABLE"
            else:
                decision_value, reason = "PASS", str(item["reason"])

            selected = item["selected"]
            companion = item["companion"]
            ref_selected = item["reference_selected"]
            ref_companion = item["reference_companion"]
            evidence = _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "lab": self._policy.lab,
                    "policy_version": self._policy.policy_version,
                    "target": [
                        selected["market_observation_id"],
                        companion["market_observation_id"],
                    ],
                    "reference": [
                        ref_selected["market_observation_id"],
                        ref_companion["market_observation_id"],
                    ],
                }
            )
            decision = ContextMarketDecision(
                decision_id="quantlab-context-decision-v1:"
                + _fingerprint(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "lab": self._policy.lab,
                        "evidence": evidence,
                        "selected_observation_id": selected["market_observation_id"],
                        "decision": decision_value,
                        "reason": reason,
                    }
                ),
                fixture_id=str(fixture["fixture_id"]),
                lab=self._policy.lab,
                decision_at=now,
                policy_version=self._policy.policy_version,
                model_name=self._policy.model_name,
                model_version=self._policy.model_version,
                bookmaker_id=int(target["bookmaker_id"]),
                bookmaker_name=str(target["bookmaker_name"]),
                reference_bookmaker_id=int(reference["bookmaker_id"]),
                reference_bookmaker_name=str(reference["bookmaker_name"]),
                provider_bet_id=int(target["provider_bet_id"]),
                provider_bet_name=str(target["provider_bet_name"]),
                market_key=self._policy.market_key,
                selection=str(item["selection"]),
                line=line,
                selected_observation_id=str(selected["market_observation_id"]),
                companion_observation_id=str(companion["market_observation_id"]),
                reference_observation_id=str(ref_selected["market_observation_id"]),
                reference_companion_observation_id=str(
                    ref_companion["market_observation_id"]
                ),
                quote_observed_at=_utc(target["captured_at"], "captured_at"),
                reference_quote_observed_at=_utc(
                    reference["captured_at"], "reference_captured_at"
                ),
                odds=float(item["odds"]),
                companion_odds=float(item["companion_odds"]),
                reference_odds=float(item["reference_odds"]),
                reference_companion_odds=float(item["reference_companion_odds"]),
                market_probability=float(item["market_probability"]),
                model_probability=float(item["model_probability"]),
                edge=float(item["edge"]),
                expected_value=float(item["expected_value"]),
                decision=decision_value,
                reason=reason,
                evidence_fingerprint=evidence,
                details={
                    "companion_selection": item["companion_selection"],
                    "target_quote_age_seconds": item["target_age_seconds"],
                    "reference_quote_age_seconds": item["reference_age_seconds"],
                    "seconds_to_kickoff": item["seconds_to_kickoff"],
                    "card_context": card_context if self._policy.lab == "CARD" else None,
                    "thresholds": {
                        "min_edge": self._policy.min_edge,
                        "min_expected_value": self._policy.min_expected_value,
                        "min_odds": self._policy.min_odds,
                        "max_odds": self._policy.max_odds,
                        "max_quote_age_seconds": self._policy.max_quote_age_seconds,
                        "min_seconds_to_kickoff": self._policy.min_seconds_to_kickoff,
                        "min_referee_sample_size": self._policy.min_referee_sample_size,
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
                            stake_minor=self._policy.flat_stake_minor,
                        )
                    )
                )

        return ReferenceEngineResult(
            decisions_inserted=decisions_inserted,
            picks_inserted=picks_inserted,
        )
