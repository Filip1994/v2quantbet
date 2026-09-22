from datetime import UTC, datetime

import pytest

from h2h.domain.model_coverage import ProductionTrainingPolicy


def test_training_policy_has_deterministic_reference_window_and_season_fallback() -> None:
    policy = ProductionTrainingPolicy(
        history_window_days=730,
        min_matches=80,
        xi=0.0018,
        ridge=0.01,
        freshness_days=14,
        previous_seasons=1,
        min_team_matches=3,
    )
    now = datetime(2026, 9, 23, 18, 42, 10, tzinfo=UTC)
    start, end = policy.training_window(now)

    assert end == datetime(2026, 9, 23, tzinfo=UTC)
    assert (end - start).days == 730
    assert policy.allowed_training_seasons(2026) == (2026, 2025)
    assert len(policy.fingerprint) == 64
    assert policy.fingerprint in policy.provenance_trainer_version


@pytest.mark.parametrize(
    "changes",
    [
        {"history_window_days": 0},
        {"min_matches": 0},
        {"xi": -0.1},
        {"ridge": float("nan")},
        {"freshness_days": 0},
        {"previous_seasons": -1},
        {"min_team_matches": 0},
    ],
)
def test_training_policy_rejects_unsafe_values(changes) -> None:
    with pytest.raises((TypeError, ValueError)):
        ProductionTrainingPolicy(**changes)


def test_policy_fingerprint_changes_for_every_decision_affecting_value() -> None:
    baseline = ProductionTrainingPolicy().fingerprint
    assert ProductionTrainingPolicy(min_matches=81).fingerprint != baseline
    assert ProductionTrainingPolicy(min_team_matches=4).fingerprint != baseline
    assert ProductionTrainingPolicy(previous_seasons=0).fingerprint != baseline
