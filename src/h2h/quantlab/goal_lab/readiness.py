"""Frozen GoalLab V1 production-readiness contract."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from h2h.quantlab.goal_lab.audit import METHOD_VERSION
from h2h.quantlab.goal_lab.model import FEATURE_VERSION, MODEL_PREFIX
from h2h.quantlab.goal_lab.picks import (
    FLAT_STAKE_MINOR,
    GOAL_RESULT_FINALITY_DELAY_SECONDS,
    GOAL_RESULT_INITIAL_DELAY_SECONDS,
    GOAL_RESULT_POSTPONED_REFRESH_SECONDS,
    GOAL_RESULT_REFRESH_SECONDS,
    PICK_POLICY_VERSION,
    SETTLEMENT_RULE_VERSION,
)
from h2h.quantlab.goal_lab.structural_shadow_engine import (
    MAX_ODDS,
    MAX_QUOTE_AGE_SECONDS,
    MIN_EDGE,
    MIN_EXPECTED_VALUE,
    MIN_ODDS,
    MIN_SECONDS_TO_KICKOFF,
    POLICY_VERSION,
    StructuralGoalPolicy,
)


GOALLAB_V1_LOCK_VERSION = "GOALLAB_V1_LOCK_2026_09_28"

LOCKED_CONTRACT: dict[str, Any] = {
    "lock_version": GOALLAB_V1_LOCK_VERSION,
    "model_prefix": "DC_PLUS_PRO_STRUCTURAL_V1:",
    "feature_version": "GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1",
    "evaluation_policy_version": "GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V2",
    "pick_policy_version": "GOALLAB_DC_PLUS_PICK_POLICY_V1",
    "settlement_rule_version": "GOALLAB_SETTLEMENT_V1",
    "validation_method_version": "GOALLAB_CHRONOLOGICAL_HOLDOUT_V3",
    "flat_stake_minor": 10_000,
    "min_edge": 0.03,
    "min_expected_value": 0.03,
    "min_odds": 1.40,
    "max_odds": 4.00,
    "max_quote_age_seconds": 13 * 60 * 60,
    "min_seconds_to_kickoff": 15 * 60,
    "goal_result_initial_delay_seconds": 6_300,
    "goal_result_refresh_seconds": 900,
    "goal_result_postponed_refresh_seconds": 21_600,
    "goal_result_finality_delay_seconds": 900,
    "canonical_markets": ("OU_25", "BTTS"),
}


def assert_goallab_v1_contract() -> dict[str, Any]:
    """Fail closed if live code drifts from the frozen GoalLab V1 contract."""

    live = {
        "model_prefix": MODEL_PREFIX,
        "feature_version": FEATURE_VERSION,
        "evaluation_policy_version": POLICY_VERSION,
        "pick_policy_version": PICK_POLICY_VERSION,
        "settlement_rule_version": SETTLEMENT_RULE_VERSION,
        "validation_method_version": METHOD_VERSION,
        "flat_stake_minor": FLAT_STAKE_MINOR,
        "min_edge": MIN_EDGE,
        "min_expected_value": MIN_EXPECTED_VALUE,
        "min_odds": MIN_ODDS,
        "max_odds": MAX_ODDS,
        "max_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
        "min_seconds_to_kickoff": MIN_SECONDS_TO_KICKOFF,
        "goal_result_initial_delay_seconds": GOAL_RESULT_INITIAL_DELAY_SECONDS,
        "goal_result_refresh_seconds": GOAL_RESULT_REFRESH_SECONDS,
        "goal_result_postponed_refresh_seconds": GOAL_RESULT_POSTPONED_REFRESH_SECONDS,
        "goal_result_finality_delay_seconds": GOAL_RESULT_FINALITY_DELAY_SECONDS,
    }
    expected = {
        key: value
        for key, value in LOCKED_CONTRACT.items()
        if key not in {"lock_version", "canonical_markets"}
    }
    if live != expected:
        drift = {
            key: {"expected": expected.get(key), "live": live.get(key)}
            for key in sorted(set(expected) | set(live))
            if expected.get(key) != live.get(key)
        }
        raise RuntimeError(f"GoalLab V1 contract drift detected: {drift}")

    defaults = StructuralGoalPolicy()
    policy = asdict(defaults)
    if policy["version"] != LOCKED_CONTRACT["evaluation_policy_version"]:
        raise RuntimeError("GoalLab V1 policy version drift detected")
    if policy["pick_policy_version"] != LOCKED_CONTRACT["pick_policy_version"]:
        raise RuntimeError("GoalLab V1 pick-policy drift detected")
    if policy["flat_stake_minor"] != LOCKED_CONTRACT["flat_stake_minor"]:
        raise RuntimeError("GoalLab V1 flat-stake drift detected")
    return dict(LOCKED_CONTRACT)
