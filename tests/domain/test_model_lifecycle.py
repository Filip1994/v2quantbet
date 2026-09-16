from datetime import UTC, datetime, timedelta, timezone

import pytest

from h2h.domain.model_lifecycle import DixonColesModelArtifact, DixonColesModelScope
from h2h.domain.model_lifecycle import DixonColesTrainingConfig


def test_scope_requires_provider_namespace_and_positive_non_bool_ids() -> None:
    assert DixonColesModelScope("api-football", "api-football", 39, 2024).league_id == 39
    with pytest.raises(TypeError, match="league_id"):
        DixonColesModelScope("api-football", "api-football", True, 2024)
    with pytest.raises(ValueError, match="team_id_namespace"):
        DixonColesModelScope("api-football", " ", 39, 2024)


@pytest.mark.parametrize(("field", "value"), [("xi", float("nan")), ("xi", -0.1), ("ridge", float("inf")), ("ridge", -0.1)])
def test_training_config_requires_finite_nonnegative_floats(field, value) -> None:
    values = {
        "reference_time": datetime(2025, 2, 1, tzinfo=UTC),
        "xi": 0.001,
        "ridge": 0.01,
        "min_matches": 80,
        "trainer_code_version": "abc123",
    }
    values[field] = value
    with pytest.raises(ValueError, match=field):
        DixonColesTrainingConfig(**values)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_training_config_requires_positive_non_bool_min_matches(value) -> None:
    with pytest.raises((TypeError, ValueError), match="min_matches"):
        DixonColesTrainingConfig(
            datetime(2025, 2, 1, tzinfo=UTC),
            0.001,
            min_matches=value,
            trainer_code_version="abc123",
        )


def test_training_config_requires_aware_utc_timestamp() -> None:
    config = DixonColesTrainingConfig(
        datetime(2025, 2, 1, 1, tzinfo=timezone.utc),
        0.001,
        trainer_code_version="abc123",
    )
    assert config.reference_time.tzinfo is UTC
    with pytest.raises(ValueError, match="timezone-aware"):
        DixonColesTrainingConfig(
            datetime(2025, 2, 1, tzinfo=UTC).replace(tzinfo=None),
            0.001,
            trainer_code_version="abc123",
        )
    with pytest.raises(ValueError, match="expressed in UTC"):
        DixonColesTrainingConfig(
            datetime(2025, 2, 1, tzinfo=timezone(timedelta(hours=1))),
            0.001,
            trainer_code_version="abc123",
        )


def test_artifact_cannot_be_caller_constructed() -> None:
    with pytest.raises(TypeError, match="trusted lifecycle"):
        DixonColesModelArtifact()
