"""Shared shadow-only value engine for count markets (corners/cards)."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from statistics import fmean
from typing import Any, Iterable

from h2h.quantlab.scope import card_corner_scope


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _fingerprint(payload: object) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _tokens(value: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def poisson_over_probability(mean: float, line: float) -> float:
    """Return P(X > line) for a Poisson count and a half-goal/count line."""
    if not math.isfinite(mean) or mean <= 0:
        raise ValueError("mean must be finite and positive")
    doubled = round(line * 2)
    if abs(line * 2 - doubled) > 1e-9 or doubled % 2 == 0:
        raise ValueError("only half-count lines are supported")
    cutoff = math.floor(line)
    term = math.exp(-mean)
    cumulative = term
    for k in range(1, cutoff + 1):
        term *= mean / k
        cumulative += term
    result = 1.0 - cumulative
    return min(1.0 - 1e-12, max(1e-12, result))


@dataclass(frozen=True, slots=True)
class CountShadowPolicy:
    min_edge: float = 0.04
    min_expected_value: float = 0.04
    min_odds: float = 1.45
    max_odds: float = 3.50
    max_quote_age_seconds: int = 13 * 60 * 60
    min_seconds_to_kickoff: int = 15 * 60
    flat_stake_minor: int = 10_000

    def __post_init__(self) -> None:
        if self.min_edge < 0 or self.min_expected_value < 0:
            raise ValueError("value thresholds must be non-negative")
        if not 1.0 < self.min_odds <= self.max_odds:
            raise ValueError("invalid odds bounds")
        if self.max_quote_age_seconds <= 0 or self.min_seconds_to_kickoff <= 0:
            raise ValueError("time thresholds must be positive")
        if self.flat_stake_minor <= 0:
            raise ValueError("flat_stake_minor must be positive")


@dataclass(frozen=True, slots=True)
class CountDecision:
    decision_id: str
    fixture_id: str
    lab: str
    decision_at: datetime
    policy_version: str
    model_name: str | None
    model_version: str | None
    bookmaker_id: int | None
    bookmaker_name: str | None
    provider_bet_id: int | None
    provider_bet_name: str | None
    market_key: str | None
    selection: str | None
    line: float | None
    selected_observation_id: str | None
    companion_observation_id: str | None
    quote_observed_at: datetime | None
    odds: float | None
    companion_odds: float | None
    market_probability: float | None
    model_probability: float | None
    edge: float | None
    expected_value: float | None
    decision: str
    reason: str
    evidence_fingerprint: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CountEngineResult:
    decisions_inserted: int = 0
    picks_inserted: int = 0


@dataclass(frozen=True, slots=True)
class ModelMean:
    mean: float | None
    model_name: str
    model_version: str
    reason: str | None
    details: dict[str, Any]


class CountLabShadowPickEngine:
    """Base engine for stored two-sided Over/Under count markets."""

    lab: str
    policy_version: str
    model_name: str
    model_version: str

    def __init__(
        self,
        repository: Any,
        *,
        policy: CountShadowPolicy | None = None,
    ) -> None:
        if self.lab not in {"CORNER", "CARD"}:
            raise ValueError("CountLab engine lab must be CORNER or CARD")
        self._repository = repository
        self._policy = policy or CountShadowPolicy()

    @staticmethod
    def _scope_kwargs(fixture: dict[str, Any]) -> dict[str, object]:
        return {
            "country": fixture.get("country"),
            "competition_name": fixture.get("competition_name"),
            "competition_type": fixture.get("competition_type"),
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
        }

    def market_allowed(self, provider_bet_name: str) -> bool:
        raise NotImplementedError

    def model_mean(self, fixture: dict[str, Any], decision_at: datetime) -> ModelMean:
        raise NotImplementedError

    def _fixture_pass(
        self,
        fixture: dict[str, Any],
        now: datetime,
        *,
        reason: str,
        model: ModelMean | None = None,
        details: dict[str, Any] | None = None,
    ) -> CountEngineResult:
        evidence = _fingerprint(
            {
                "fixture_id": fixture["fixture_id"],
                "lab": self.lab,
                "policy_version": self.policy_version,
                "reason": reason,
                "model_version": None if model is None else model.model_version,
                "details": details or {},
            }
        )
        decision = CountDecision(
            decision_id="quantlab-count-decision-v1:"
            + _fingerprint(
                {
                    "fixture_id": fixture["fixture_id"],
                    "lab": self.lab,
                    "evidence": evidence,
                    "reason": reason,
                }
            ),
            fixture_id=str(fixture["fixture_id"]),
            lab=self.lab,
            decision_at=now,
            policy_version=self.policy_version,
            model_name=None if model is None else model.model_name,
            model_version=None if model is None else model.model_version,
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
            details={**({} if model is None else model.details), **(details or {})},
        )
        inserted = self._repository.save_count_decision(decision)
        return CountEngineResult(decisions_inserted=int(bool(inserted)))

    def _pairs(
        self, rows: Iterable[dict[str, Any]]
    ) -> tuple[dict[str, Any], ...]:
        grouped: dict[tuple[int, int, str, datetime, float], dict[str, dict[str, Any]]] = {}
        for row in rows:
            name = str(row["provider_bet_name"])
            if not self.market_allowed(name):
                continue
            raw = str(row["raw_selection"] or "").strip().casefold()
            line_raw = row.get("parsed_line")
            if line_raw is None:
                continue
            line = float(line_raw)
            doubled = round(line * 2)
            if abs(line * 2 - doubled) > 1e-9 or doubled % 2 == 0:
                continue
            if raw != f"over {line:g}" and raw != f"under {line:g}":
                continue
            selection = "OVER" if raw.startswith("over ") else "UNDER"
            key = (
                int(row["bookmaker_id"]),
                int(row["provider_bet_id"]),
                name,
                row["captured_at"],
                line,
            )
            grouped.setdefault(key, {})[selection] = row

        latest: dict[tuple[int, int, str, float], dict[str, Any]] = {}
        for key, selections in grouped.items():
            if set(selections) != {"OVER", "UNDER"}:
                continue
            bookmaker_id, bet_id, name, captured_at, line = key
            pair = {
                "bookmaker_id": bookmaker_id,
                "bookmaker_name": selections["OVER"]["bookmaker_name"],
                "provider_bet_id": bet_id,
                "provider_bet_name": name,
                "market_key": f"{self.lab}_TOTAL_{line:g}",
                "line": line,
                "captured_at": captured_at,
                "selections": selections,
            }
            logical = (bookmaker_id, bet_id, name, line)
            current = latest.get(logical)
            if current is None or captured_at > current["captured_at"]:
                latest[logical] = pair
        return tuple(
            sorted(
                latest.values(),
                key=lambda item: (
                    float(item["line"]),
                    int(item["bookmaker_id"]),
                    int(item["provider_bet_id"]),
                ),
            )
        )

    def run_fixture(self, fixture: dict[str, Any], *, decision_at: datetime) -> CountEngineResult:
        now = _utc(decision_at, "decision_at")
        kickoff = _utc(fixture["kickoff_at"], "kickoff_at")

        if not card_corner_scope(**self._scope_kwargs(fixture)).allowed:
            return self._fixture_pass(fixture, now, reason="OUTSIDE_CARD_CORNER_SCOPE")

        model = self.model_mean(fixture, now)
        if model.reason is not None or model.mean is None:
            return self._fixture_pass(
                fixture,
                now,
                reason=model.reason or "MODEL_UNAVAILABLE",
                model=model,
            )
        if not math.isfinite(model.mean) or model.mean <= 0:
            return self._fixture_pass(
                fixture,
                now,
                reason="INVALID_MODEL_MEAN",
                model=model,
            )

        rows = self._repository.count_market_rows(
            str(fixture["fixture_id"]),
            lab=self.lab,
            decision_at=now,
        )
        pairs = self._pairs(rows)
        if not pairs:
            return self._fixture_pass(
                fixture,
                now,
                reason=f"NO_CANONICAL_{self.lab}_MARKET",
                model=model,
            )

        evidence_ids = sorted(
            str(side["market_observation_id"])
            for pair in pairs
            for side in pair["selections"].values()
        )
        evidence = _fingerprint(
            {
                "fixture_id": fixture["fixture_id"],
                "lab": self.lab,
                "policy_version": self.policy_version,
                "model_version": model.model_version,
                "model_details": model.details,
                "observation_ids": evidence_ids,
            }
        )

        evaluated: list[dict[str, Any]] = []
        for pair in pairs:
            over_probability = poisson_over_probability(model.mean, float(pair["line"]))
            for selection, companion_selection in (("OVER", "UNDER"), ("UNDER", "OVER")):
                selected = pair["selections"][selection]
                companion = pair["selections"][companion_selection]
                odds = float(selected["odds"])
                companion_odds = float(companion["odds"])
                raw_selected = 1.0 / odds
                raw_companion = 1.0 / companion_odds
                market_probability = raw_selected / (raw_selected + raw_companion)
                model_probability = (
                    over_probability if selection == "OVER" else 1.0 - over_probability
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

        winners: dict[tuple[str, str, float], dict[str, Any]] = {}
        for item in evaluated:
            if item["reason"] is not None:
                continue
            pair = item["pair"]
            key = (
                str(pair["market_key"]),
                str(item["selection"]),
                float(pair["line"]),
            )
            current = winners.get(key)
            if current is None or (item["odds"], -int(pair["bookmaker_id"])) > (
                current["odds"],
                -int(current["pair"]["bookmaker_id"]),
            ):
                winners[key] = item

        decisions_inserted = 0
        picks_inserted = 0
        for item in evaluated:
            pair = item["pair"]
            key = (
                str(pair["market_key"]),
                str(item["selection"]),
                float(pair["line"]),
            )
            if item["reason"] is None:
                if winners.get(key) is item:
                    decision_value, reason = "PICK", "VALUE_THRESHOLD_PASSED"
                else:
                    decision_value, reason = "PASS", "BETTER_PRICE_AVAILABLE"
            else:
                decision_value, reason = "PASS", str(item["reason"])

            selected = item["selected"]
            companion = item["companion"]
            decision = CountDecision(
                decision_id="quantlab-count-decision-v1:"
                + _fingerprint(
                    {
                        "fixture_id": fixture["fixture_id"],
                        "lab": self.lab,
                        "evidence": evidence,
                        "selected_observation_id": selected["market_observation_id"],
                        "companion_observation_id": companion["market_observation_id"],
                        "decision": decision_value,
                        "reason": reason,
                    }
                ),
                fixture_id=str(fixture["fixture_id"]),
                lab=self.lab,
                decision_at=now,
                policy_version=self.policy_version,
                model_name=model.model_name,
                model_version=model.model_version,
                bookmaker_id=int(pair["bookmaker_id"]),
                bookmaker_name=str(pair["bookmaker_name"]),
                provider_bet_id=int(pair["provider_bet_id"]),
                provider_bet_name=str(pair["provider_bet_name"]),
                market_key=str(pair["market_key"]),
                selection=str(item["selection"]),
                line=float(pair["line"]),
                selected_observation_id=str(selected["market_observation_id"]),
                companion_observation_id=str(companion["market_observation_id"]),
                quote_observed_at=_utc(pair["captured_at"], "captured_at"),
                odds=float(item["odds"]),
                companion_odds=float(item["companion_odds"]),
                market_probability=float(item["market_probability"]),
                model_probability=float(item["model_probability"]),
                edge=float(item["edge"]),
                expected_value=float(item["expected_value"]),
                decision=decision_value,
                reason=reason,
                evidence_fingerprint=evidence,
                details={
                    **model.details,
                    "companion_selection": item["companion_selection"],
                    "quote_age_seconds": item["quote_age_seconds"],
                    "seconds_to_kickoff": item["seconds_to_kickoff"],
                    "thresholds": {
                        "min_edge": self._policy.min_edge,
                        "min_expected_value": self._policy.min_expected_value,
                        "min_odds": self._policy.min_odds,
                        "max_odds": self._policy.max_odds,
                        "max_quote_age_seconds": self._policy.max_quote_age_seconds,
                        "min_seconds_to_kickoff": self._policy.min_seconds_to_kickoff,
                    },
                },
            )
            inserted = bool(self._repository.save_count_decision(decision))
            decisions_inserted += int(inserted)
            if decision_value == "PICK" and inserted:
                picks_inserted += int(
                    bool(
                        self._repository.save_count_shadow_bet(
                            decision,
                            stake_minor=self._policy.flat_stake_minor,
                        )
                    )
                )

        return CountEngineResult(decisions_inserted, picks_inserted)


def mean(values: Iterable[float]) -> float:
    items = tuple(float(value) for value in values)
    if not items:
        raise ValueError("cannot average an empty sample")
    return float(fmean(items))


def market_tokens(value: object) -> set[str]:
    return _tokens(value)
