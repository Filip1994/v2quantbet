from datetime import UTC, datetime, timedelta

import pytest

from h2h.domain.pick_monitoring import (
    ClosingFinalization,
    ClosingOutcome,
    MonitoringRecord,
    MonitoringState,
    OddsCheckpoint,
    OddsLifecyclePolicy,
)


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


def policy(**changes):
    values = {
        "monitoring_interval_seconds": 300,
        "current_max_age_seconds": 600,
        "closing_max_age_seconds": 900,
    }
    values.update(changes)
    return OddsLifecyclePolicy(**values)


def test_lifecycle_policy_requires_explicit_positive_values() -> None:
    assert policy().version == "ODDS_LIFECYCLE_V1"
    with pytest.raises(ValueError, match="closing_max_age_seconds"):
        policy(closing_max_age_seconds=0)


def test_monitoring_record_enforces_state_projection_shape() -> None:
    value = MonitoringRecord(
        "pick", MonitoringState.MONITORING, policy(), NOW, NOW, NOW, 1
    )
    assert value.next_refresh_at == NOW
    with pytest.raises(ValueError, match="cannot have next_refresh_at"):
        MonitoringRecord(
            "pick", MonitoringState.CLOSED_FOR_ODDS, policy(), NOW, NOW, NOW, 2
        )


def test_checkpoint_freshness_checks_observed_and_captured_ages() -> None:
    fresh = OddsCheckpoint("snap", "series", 2.0, NOW, NOW, "source")
    provider_stale = OddsCheckpoint(
        "snap", "series", 2.0, NOW - timedelta(minutes=20), NOW, "source"
    )
    assert fresh.is_fresh_at(NOW + timedelta(minutes=15), 900)
    assert not provider_stale.is_fresh_at(NOW, 900)


def test_closing_outcomes_enforce_snapshot_shape() -> None:
    captured = ClosingFinalization(
        "final", "pick", "fixture", "observation", NOW, "series", "source", NOW,
        ClosingOutcome.CAPTURED, "snapshot", "snapshot", "ODDS_LIFECYCLE_V1", 900,
    )
    assert captured.closing_snapshot_id == "snapshot"
    with pytest.raises(ValueError, match="NO_VALID_QUOTE"):
        ClosingFinalization(
            "final", "pick", "fixture", "observation", NOW, "series", "source", NOW,
            ClosingOutcome.NO_VALID_QUOTE, "snapshot", None, "ODDS_LIFECYCLE_V1", 900,
        )
