"""GoalLab V1 shadow-only decision engine over persisted two-sided goal markets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import isfinite
from typing import Any

from h2h.domain.fixture_identity import API_FOOTBALL_PROVIDER
from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.quant.dixon_coles import DixonColesFitError
from h2h.quantlab.scope import goal_scope


POLICY_VERSION = "GOALLAB_SHADOW_POLICY_V1"
MODEL_NAME = "Dixon-Coles Control"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class GoalLabShadowPolicy:
    min_edge: float = 0.03
    min_expected_value: float = 0.03
    min_odds: float = 1.40
    max_odds: float = 4.00
    max_quote_age_seconds: int = 13 * 60 * 60
    min_seconds_to_kickoff: int = 15 * 60
    flat_stake_minor: int = 10_000
    version: str = POLICY_VERSION

    def __post_init__(self) -> None:
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
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not self.version.strip():
            raise ValueError("version must not be blank")


@dataclass(frozen=True, slots=True)
class GoalDecision:
    decision_id: str
    fixture_id: str
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
class GoalEngineResult:
    decisions_inserted: int = 0
    picks_inserted: int = 0


class GoalLabShadowPickEngine:
    """Evaluate stored GoalLab quotes; it has no provider or production-write dependency."""

    def __init__(
        self,
        repository: Any,
        model_loader: Any,
        *,
        policy: GoalLabShadowPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._model_loader = model_loader
        self._policy = policy or GoalLabShadowPolicy()

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
        evidence = _fingerprint(
            {
                "fixture_id": fixture["fixture_id"],
                "league_id": fixture.get("league_id"),
                "season": fixture.get("season"),
                "model_version": model_version,
                "policy_version": self._policy.version,
                "reason": reason,
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
            details=dict(details or {}),
        )
        inserted = self._repository.save_goal_decision(decision)
        return GoalEngineResult(decisions_inserted=int(bool(inserted)))

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
            raise ValueError("model probability must be finite and strictly between 0 and 1")
        return result

    def run_fixture(self, fixture: dict[str, Any], *, decision_at: datetime) -> GoalEngineResult:
        now = _utc(decision_at, "decision_at")
        fixture_id = str(fixture["fixture_id"])
        kickoff = _utc(fixture["kickoff_at"], "kickoff_at")

        if not goal_scope(**self._scope_kwargs(fixture)).allowed:
            return self._fixture_pass(fixture, now, reason="OUTSIDE_GOAL_SCOPE")

        required = ("league_id", "season", "home_team_id", "away_team_id")
        if any(fixture.get(name) is None for name in required):
            return self._fixture_pass(
                fixture,
                now,
                reason="MISSING_FIXTURE_MODEL_DIMENSIONS",
                details={"missing": [name for name in required if fixture.get(name) is None]},
            )

        scope = DixonColesModelScope(
            API_FOOTBALL_PROVIDER,
            API_FOOTBALL_PROVIDER,
            int(fixture["league_id"]),
            int(fixture["season"]),
        )
        try:
            loaded = self._model_loader.execute(scope)
        except ActiveModelUnavailableError:
            return self._fixture_pass(fixture, now, reason="NO_ACTIVE_MODEL")

        model_version = str(loaded.model_version_id)
        try:
            probabilities = loaded.model.market_probabilities(
                int(fixture["home_team_id"]),
                int(fixture["away_team_id"]),
            )
        except DixonColesFitError as exc:
            return self._fixture_pass(
                fixture,
                now,
                reason="MODEL_TEAM_UNCOVERED",
                model_version=model_version,
                details={"error_class": type(exc).__name__, "error_message": str(exc)},
            )

        pairs = tuple(
            self._repository.goal_market_pairs(fixture_id, decision_at=now)
        )
        if not pairs:
            return self._fixture_pass(
                fixture,
                now,
                reason="NO_COMPLETE_GOAL_MARKET",
                model_version=model_version,
            )

        evidence_ids = sorted(
            {
                str(side["market_observation_id"])
                for pair in pairs
                for side in pair["selections"].values()
            }
        )
        evidence = _fingerprint(
            {
                "fixture_id": fixture_id,
                "model_version": model_version,
                "policy_version": self._policy.version,
                "observation_ids": evidence_ids,
            }
        )

        evaluated: list[dict[str, Any]] = []
        for pair in pairs:
            market_key = str(pair["market_key"])
            selections = dict(pair["selections"])
            for selection, companion_selection in (
                (("OVER", "UNDER") if market_key == "OU_25" else ("YES", "NO")),
                (("UNDER", "OVER") if market_key == "OU_25" else ("NO", "YES")),
            ):
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
            key = (
                str(pair["market_key"]),
                str(item["selection"]),
                None if pair.get("line") is None else float(pair["line"]),
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
            line = None if pair.get("line") is None else float(pair["line"])
            key = (str(pair["market_key"]), str(item["selection"]), line)
            if item["reason"] is None:
                if winners.get(key) is item:
                    decision_value, reason = "PICK", "VALUE_THRESHOLD_PASSED"
                else:
                    decision_value, reason = "PASS", "BETTER_PRICE_AVAILABLE"
            else:
                decision_value, reason = "PASS", str(item["reason"])

            selected = item["selected"]
            companion = item["companion"]
            decision_id = "quantlab-goal-decision-v1:" + _fingerprint(
                {
                    "fixture_id": fixture_id,
                    "evidence": evidence,
                    "selected_observation_id": selected["market_observation_id"],
                    "companion_observation_id": companion["market_observation_id"],
                    "decision": decision_value,
                    "reason": reason,
                }
            )
            decision = GoalDecision(
                decision_id=decision_id,
                fixture_id=fixture_id,
                decision_at=now,
                policy_version=self._policy.version,
                model_name=MODEL_NAME,
                model_version=model_version,
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
                decision=decision_value,
                reason=reason,
                evidence_fingerprint=evidence,
                details={
                    "companion_selection": item["companion_selection"],
                    "quote_age_seconds": item["quote_age_seconds"],
                    "seconds_to_kickoff": item["seconds_to_kickoff"],
                    "provider_updated_at": selected.get("provider_updated_at"),
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
            decisions_inserted += int(bool(self._repository.save_goal_decision(decision)))
            if decision_value == "PICK":
                picks_inserted += int(
                    bool(
                        self._repository.save_goal_shadow_bet(
                            decision,
                            stake_minor=self._policy.flat_stake_minor,
                        )
                    )
                )

        return GoalEngineResult(
            decisions_inserted=decisions_inserted,
            picks_inserted=picks_inserted,
        )
