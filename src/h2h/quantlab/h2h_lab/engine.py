"""H2HLab V1: plain Dixon-Coles probability blended with direct H2H evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from h2h.domain.fixture_identity import API_FOOTBALL_PROVIDER
from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.quant.dixon_coles import DixonColesFitError
from h2h.quantlab.h2h_lab.experiment import (
    EXPERIMENT_VERSION,
    arm_relation,
    canonical_arm,
    probability_trials,
    should_freeze,
)
from h2h.quantlab.scope import goal_scope

POLICY_VERSION = "H2HLAB_DC_H2H_POLICY_V1"
MODEL_NAME = "DC + H2H Composite"
MIN_H2H_MATCHES = 5
MAX_H2H_MATCHES = 10
MIN_EDGE = 0.03
MIN_EXPECTED_VALUE = 0.03
MIN_ODDS = 1.40
MAX_ODDS = 4.00
MAX_QUOTE_AGE_SECONDS = 13 * 60 * 60
MIN_SECONDS_TO_KICKOFF = 15 * 60
FLAT_STAKE_MINOR = 10_000


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _fingerprint(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def dc_weight_for_sample(sample_size: int) -> float:
    """V1 policy: DC never exceeds 70%; H2H gains weight as direct sample grows."""
    if sample_size < MIN_H2H_MATCHES:
        raise ValueError("H2H sample must contain at least five direct meetings")
    capped = min(MAX_H2H_MATCHES, sample_size)
    return max(0.60, 0.70 - 0.02 * (capped - MIN_H2H_MATCHES))


def _selection_probability(probabilities: dict[str, float], market_key: str, selection: str) -> float:
    if market_key == "OU_25":
        key = "OVER_2_5" if selection == "OVER" else "UNDER_2_5"
        value = probabilities[key]
    elif market_key == "BTTS":
        yes = float(probabilities["BTTS_YES"])
        value = yes if selection == "YES" else 1.0 - yes
    else:
        raise ValueError(f"unsupported H2HLab market {market_key!r}")
    result = float(value)
    if not isfinite(result) or not 0.0 < result < 1.0:
        raise ValueError("DC probability must be finite and inside (0, 1)")
    return result


def _h2h_event(meeting: dict[str, Any], market_key: str, selection: str) -> bool:
    home = int(meeting["home_goals"])
    away = int(meeting["away_goals"])
    if market_key == "OU_25":
        over = home + away > 2.5
        return over if selection == "OVER" else not over
    if market_key == "BTTS":
        yes = home > 0 and away > 0
        return yes if selection == "YES" else not yes
    raise ValueError(f"unsupported H2HLab market {market_key!r}")


def h2h_probability(
    meetings: tuple[dict[str, Any], ...],
    *,
    target_home_team_id: int,
    target_away_team_id: int,
    market_key: str,
    selection: str,
) -> tuple[float, float, tuple[dict[str, Any], ...]]:
    """Recency×venue weighted direct-H2H rate with symmetric Beta(2,2) shrinkage."""
    if len(meetings) < MIN_H2H_MATCHES:
        raise ValueError("minimum five direct H2H matches required")
    selected = meetings[:MAX_H2H_MATCHES]
    success_weight = 0.0
    total_weight = 0.0
    evidence: list[dict[str, Any]] = []
    for index, meeting in enumerate(selected):
        same_venue = (
            int(meeting["home_team_id"]) == target_home_team_id
            and int(meeting["away_team_id"]) == target_away_team_id
        )
        recency_weight = 0.90 ** index
        venue_weight = 1.0 if same_venue else 0.75
        weight = recency_weight * venue_weight
        hit = _h2h_event(meeting, market_key, selection)
        total_weight += weight
        success_weight += weight if hit else 0.0
        evidence.append(
            {
                **meeting,
                "same_venue": same_venue,
                "recency_weight": round(recency_weight, 6),
                "venue_weight": venue_weight,
                "final_weight": round(weight, 6),
                "selection_hit": hit,
            }
        )
    raw = success_weight / total_weight
    shrunk = (success_weight + 2.0) / (total_weight + 4.0)
    return raw, shrunk, tuple(evidence)


@dataclass(frozen=True, slots=True)
class H2HDecision:
    decision_id: str
    fixture_id: str
    lab: str
    h2h_snapshot_id: str | None
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
    dc_probability: float | None
    h2h_probability: float | None
    dc_weight: float | None
    h2h_weight: float | None
    model_probability: float | None
    edge: float | None
    expected_value: float | None
    h2h_sample_size: int
    decision: str
    reason: str
    evidence_fingerprint: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class H2HEngineResult:
    decisions_inserted: int = 0
    picks_inserted: int = 0
    experiments_inserted: int = 0


class H2HLabEngine:
    def __init__(self, repository: Any, model_loader: Any) -> None:
        self._repository = repository
        self._model_loader = model_loader

    @staticmethod
    def _scope_kwargs(fixture: dict[str, Any]) -> dict[str, object]:
        return {
            "country": fixture.get("country"),
            "competition_name": fixture.get("competition_name"),
            "competition_type": fixture.get("competition_type"),
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
            "league_id": fixture.get("league_id"),
        }

    def _pass(self, fixture: dict[str, Any], now: datetime, *, reason: str, sample_size: int = 0, snapshot_id: str | None = None, model_version: str | None = None, details: dict[str, Any] | None = None) -> H2HEngineResult:
        evidence = _fingerprint({"fixture_id": fixture["fixture_id"], "policy": POLICY_VERSION, "reason": reason, "snapshot": snapshot_id, "details": details or {}})
        item = H2HDecision(
            decision_id="quantlab-h2h-decision-v1:" + _fingerprint({"fixture": fixture["fixture_id"], "evidence": evidence}),
            fixture_id=str(fixture["fixture_id"]), lab="H2H", h2h_snapshot_id=snapshot_id,
            decision_at=now, policy_version=POLICY_VERSION, model_name=None if model_version is None else MODEL_NAME,
            model_version=model_version, bookmaker_id=None, bookmaker_name=None, provider_bet_id=None,
            provider_bet_name=None, market_key=None, selection=None, line=None, selected_observation_id=None,
            companion_observation_id=None, quote_observed_at=None, odds=None, companion_odds=None,
            market_probability=None, dc_probability=None, h2h_probability=None, dc_weight=None, h2h_weight=None,
            model_probability=None, edge=None, expected_value=None, h2h_sample_size=sample_size,
            decision="PASS", reason=reason, evidence_fingerprint=evidence, details=dict(details or {}),
        )
        return H2HEngineResult(decisions_inserted=int(bool(self._repository.save_h2h_decision(item))))

    def run_fixture(self, fixture: dict[str, Any], *, decision_at: datetime) -> H2HEngineResult:
        now = _utc(decision_at, "decision_at")
        fixture_id = str(fixture["fixture_id"])
        if not goal_scope(**self._scope_kwargs(fixture)).allowed:
            return self._pass(fixture, now, reason="OUTSIDE_GOAL_SCOPE")
        required = ("league_id", "season", "home_team_id", "away_team_id")
        missing = [name for name in required if fixture.get(name) is None]
        if missing:
            return self._pass(fixture, now, reason="MISSING_FIXTURE_MODEL_DIMENSIONS", details={"missing": missing})

        snapshot = self._repository.latest_h2h_snapshot(fixture_id, decision_at=now)
        if snapshot is None:
            return self._pass(fixture, now, reason="NO_H2H_SNAPSHOT")
        meetings = tuple(snapshot.get("meetings") or ())
        sample_size = min(len(meetings), MAX_H2H_MATCHES)
        if sample_size < MIN_H2H_MATCHES:
            return self._pass(
                fixture, now, reason="H2H_SAMPLE_BELOW_MINIMUM", sample_size=sample_size,
                snapshot_id=str(snapshot["h2h_snapshot_id"]),
                details={"minimum": MIN_H2H_MATCHES, "sample_size": sample_size},
            )

        scope = DixonColesModelScope(
            API_FOOTBALL_PROVIDER, API_FOOTBALL_PROVIDER, int(fixture["league_id"]), int(fixture["season"])
        )
        try:
            loaded = self._model_loader.execute(scope)
        except ActiveModelUnavailableError:
            return self._pass(fixture, now, reason="NO_ACTIVE_DC_MODEL", sample_size=sample_size, snapshot_id=str(snapshot["h2h_snapshot_id"]))
        model_version = str(loaded.model_version_id)
        try:
            dc_markets = loaded.model.market_probabilities(int(fixture["home_team_id"]), int(fixture["away_team_id"]))
        except DixonColesFitError as exc:
            return self._pass(
                fixture, now, reason="DC_TEAM_UNCOVERED", sample_size=sample_size,
                snapshot_id=str(snapshot["h2h_snapshot_id"]), model_version=model_version,
                details={"error_class": type(exc).__name__, "error_message": str(exc)},
            )

        pairs = tuple(self._repository.goal_market_pairs(fixture_id, decision_at=now))
        if not pairs:
            return self._pass(
                fixture, now, reason="NO_COMPLETE_GOAL_MARKET", sample_size=sample_size,
                snapshot_id=str(snapshot["h2h_snapshot_id"]), model_version=model_version,
            )

        kickoff = _utc(fixture["kickoff_at"], "kickoff_at")
        dc_weight = dc_weight_for_sample(sample_size)
        h2h_weight = 1.0 - dc_weight
        evaluated: list[dict[str, Any]] = []
        for pair in pairs:
            market_key = str(pair["market_key"])
            selections = dict(pair["selections"])
            directions = (("OVER", "UNDER"), ("UNDER", "OVER")) if market_key == "OU_25" else (("YES", "NO"), ("NO", "YES"))
            for selection, companion_selection in directions:
                selected = selections[selection]
                companion = selections[companion_selection]
                odds = float(selected["odds"])
                companion_odds = float(companion["odds"])
                raw_selected, raw_companion = 1.0 / odds, 1.0 / companion_odds
                market_probability = raw_selected / (raw_selected + raw_companion)
                dc_probability = _selection_probability(dc_markets, market_key, selection)
                h2h_raw, h2h_shrunk, evidence_meetings = h2h_probability(
                    meetings,
                    target_home_team_id=int(fixture["home_team_id"]),
                    target_away_team_id=int(fixture["away_team_id"]),
                    market_key=market_key, selection=selection,
                )
                composite = dc_weight * dc_probability + h2h_weight * h2h_shrunk
                edge = composite - market_probability
                ev = composite * odds - 1.0
                captured_at = _utc(pair["captured_at"], "captured_at")
                quote_age = (now - captured_at).total_seconds()
                seconds_to_kickoff = (kickoff - now).total_seconds()
                common_reason = None
                if seconds_to_kickoff < MIN_SECONDS_TO_KICKOFF:
                    common_reason = "KICKOFF_TOO_CLOSE"
                elif quote_age < 0:
                    common_reason = "QUOTE_FROM_FUTURE"
                elif quote_age > MAX_QUOTE_AGE_SECONDS:
                    common_reason = "STALE_QUOTE"
                elif not MIN_ODDS <= odds <= MAX_ODDS:
                    common_reason = "ODDS_OUTSIDE_RANGE"

                dc_edge = dc_probability - market_probability
                dc_ev = dc_probability * odds - 1.0
                dc_reason = common_reason
                if dc_reason is None and dc_edge < MIN_EDGE:
                    dc_reason = "EDGE_BELOW_MINIMUM"
                elif dc_reason is None and dc_ev < MIN_EXPECTED_VALUE:
                    dc_reason = "EV_BELOW_MINIMUM"

                reason = common_reason
                if reason is None and edge < MIN_EDGE:
                    reason = "EDGE_BELOW_MINIMUM"
                elif reason is None and ev < MIN_EXPECTED_VALUE:
                    reason = "EV_BELOW_MINIMUM"
                agreement = "CONFIRM" if (dc_probability - 0.5) * (h2h_shrunk - 0.5) > 0 else "CONFLICT" if (dc_probability - 0.5) * (h2h_shrunk - 0.5) < 0 else "NEUTRAL"
                evaluated.append({
                    "pair": pair, "selection": selection, "companion_selection": companion_selection,
                    "selected": selected, "companion": companion, "odds": odds, "companion_odds": companion_odds,
                    "market_probability": market_probability, "dc_probability": dc_probability,
                    "h2h_raw_probability": h2h_raw, "h2h_probability": h2h_shrunk,
                    "model_probability": composite, "edge": edge, "expected_value": ev,
                    "dc_edge": dc_edge, "dc_expected_value": dc_ev,
                    "quote_age_seconds": quote_age, "seconds_to_kickoff": seconds_to_kickoff,
                    "common_reason": common_reason, "dc_reason": dc_reason,
                    "reason": reason, "agreement": agreement, "meetings": evidence_meetings,
                })

        experiments_inserted = 0
        if should_freeze(evaluated):
            dc_arm = canonical_arm(
                evaluated,
                arm="DC_ONLY",
                reason_key="dc_reason",
                probability_key="dc_probability",
                edge_key="dc_edge",
                ev_key="dc_expected_value",
            )
            h2h_arm = canonical_arm(
                evaluated,
                arm="DC_H2H",
                reason_key="reason",
                probability_key="model_probability",
                edge_key="edge",
                ev_key="expected_value",
            )
            trials = probability_trials(evaluated)
            relation = arm_relation(dc_arm, h2h_arm)
            experiment_evidence = _fingerprint(
                {
                    "fixture_id": fixture_id,
                    "experiment_version": EXPERIMENT_VERSION,
                    "snapshot": snapshot["h2h_snapshot_id"],
                    "model_version": model_version,
                    "frozen_at": now.isoformat(),
                    "dc_arm": dc_arm,
                    "h2h_arm": h2h_arm,
                    "trials": trials,
                    "dc_weight": dc_weight,
                    "h2h_weight": h2h_weight,
                }
            )
            experiments_inserted = int(
                bool(
                    self._repository.save_h2h_experiment(
                        experiment_id="quantlab-h2h-experiment-v1:"
                        + _fingerprint(
                            {
                                "fixture_id": fixture_id,
                                "experiment_version": EXPERIMENT_VERSION,
                            }
                        ),
                        fixture_id=fixture_id,
                        h2h_snapshot_id=str(snapshot["h2h_snapshot_id"]),
                        frozen_at=now,
                        experiment_version=EXPERIMENT_VERSION,
                        model_version=model_version,
                        h2h_sample_size=sample_size,
                        dc_weight=dc_weight,
                        h2h_weight=h2h_weight,
                        relation=relation,
                        dc_arm=dc_arm,
                        h2h_arm=h2h_arm,
                        probability_trials=trials,
                        evidence_fingerprint=experiment_evidence,
                    )
                )
            )

        eligible = [item for item in evaluated if item["reason"] is None]
        canonical = max(
            eligible,
            key=lambda item: (item["expected_value"], item["edge"], item["model_probability"], item["odds"], -int(item["pair"]["bookmaker_id"])),
            default=None,
        )
        existing_pick = self._repository.context_shadow_bet_exists(fixture_id, lab="H2H")
        decisions = picks = 0
        for item in evaluated:
            pair = item["pair"]
            if item["reason"] is not None:
                decision, reason = "PASS", str(item["reason"])
            elif item is canonical and not existing_pick:
                decision, reason = "PICK", "CANONICAL_DC_H2H_VALUE_PICK"
            elif item is canonical:
                decision, reason = "PASS", "H2H_PICK_ALREADY_FROZEN"
            else:
                decision, reason = "PASS", "QUALIFIED_NOT_CANONICAL_FIXTURE_PICK"
            evidence = _fingerprint({
                "fixture_id": fixture_id, "snapshot": snapshot["h2h_snapshot_id"], "model_version": model_version,
                "policy": POLICY_VERSION, "selected": item["selected"]["market_observation_id"],
                "companion": item["companion"]["market_observation_id"], "selection": item["selection"],
                "dc_weight": dc_weight, "h2h_weight": h2h_weight,
            })
            detail = {
                "dc_probability": item["dc_probability"], "h2h_raw_probability": item["h2h_raw_probability"],
                "h2h_probability": item["h2h_probability"], "composite_probability": item["model_probability"],
                "dc_weight": dc_weight, "h2h_weight": h2h_weight, "h2h_sample_size": sample_size,
                "agreement": item["agreement"], "meetings": list(item["meetings"]),
                "quote_age_seconds": item["quote_age_seconds"], "seconds_to_kickoff": item["seconds_to_kickoff"],
                "shrinkage_prior": {"alpha": 2.0, "beta": 2.0},
                "weight_policy": "recency=0.90^index; same venue=1.00; reverse venue=0.75",
                "thresholds": {"min_h2h_matches": 5, "max_h2h_matches": 10, "max_dc_weight": 0.70, "min_edge": MIN_EDGE, "min_expected_value": MIN_EXPECTED_VALUE, "min_odds": MIN_ODDS, "max_odds": MAX_ODDS},
            }
            row = H2HDecision(
                decision_id="quantlab-h2h-decision-v1:" + _fingerprint({"fixture": fixture_id, "evidence": evidence, "decision": decision, "reason": reason}),
                fixture_id=fixture_id, lab="H2H", h2h_snapshot_id=str(snapshot["h2h_snapshot_id"]),
                decision_at=now, policy_version=POLICY_VERSION, model_name=MODEL_NAME, model_version=model_version,
                bookmaker_id=int(pair["bookmaker_id"]), bookmaker_name=str(pair["bookmaker_name"]),
                provider_bet_id=int(pair["provider_bet_id"]), provider_bet_name=str(pair["provider_bet_name"]),
                market_key=str(pair["market_key"]), selection=str(item["selection"]),
                line=None if pair.get("line") is None else float(pair["line"]),
                selected_observation_id=str(item["selected"]["market_observation_id"]),
                companion_observation_id=str(item["companion"]["market_observation_id"]),
                quote_observed_at=_utc(pair["captured_at"], "captured_at"), odds=float(item["odds"]),
                companion_odds=float(item["companion_odds"]), market_probability=float(item["market_probability"]),
                dc_probability=float(item["dc_probability"]), h2h_probability=float(item["h2h_probability"]),
                dc_weight=dc_weight, h2h_weight=h2h_weight, model_probability=float(item["model_probability"]),
                edge=float(item["edge"]), expected_value=float(item["expected_value"]), h2h_sample_size=sample_size,
                decision=decision, reason=reason, evidence_fingerprint=evidence, details=detail,
            )
            inserted = bool(self._repository.save_h2h_decision(row))
            decisions += int(inserted)
            if decision == "PICK" and inserted:
                picks += int(bool(self._repository.save_context_shadow_bet(row, stake_minor=FLAT_STAKE_MINOR)))
        return H2HEngineResult(
            decisions_inserted=decisions,
            picks_inserted=picks,
            experiments_inserted=experiments_inserted,
        )
