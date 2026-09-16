"""Immutable, model-version-bearing production prediction records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be expressed in UTC")
    return value.astimezone(UTC)


def _probability(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    result = float(value)
    if not isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be finite and between 0 and 1")
    return result


@dataclass(frozen=True, slots=True)
class PersistedFixturePrediction:
    prediction_id: str
    fixture_id: str
    fixture_observation_id: str
    model_version_id: str
    active_generation: int
    model_activated_at: datetime
    provider: str
    team_id_namespace: str
    league_id: int
    season: int
    provider_home_team_id: int
    provider_away_team_id: int
    prediction_method_version: str
    max_goals: int
    over_2_5_probability: float
    under_2_5_probability: float
    btts_yes_probability: float
    predicted_at: datetime
    persisted_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "prediction_id",
            "fixture_id",
            "fixture_observation_id",
            "model_version_id",
            "provider",
            "team_id_namespace",
            "prediction_method_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        for name in (
            "active_generation",
            "league_id",
            "season",
            "provider_home_team_id",
            "provider_away_team_id",
            "max_goals",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.provider_home_team_id == self.provider_away_team_id:
            raise ValueError("provider home and away team IDs must be different")
        for name in ("model_activated_at", "predicted_at", "persisted_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        for name in (
            "over_2_5_probability",
            "under_2_5_probability",
            "btts_yes_probability",
        ):
            object.__setattr__(self, name, _probability(getattr(self, name), name))

    @property
    def probabilities(self) -> dict[str, float]:
        return {
            "OVER_2_5": self.over_2_5_probability,
            "UNDER_2_5": self.under_2_5_probability,
            "BTTS_YES": self.btts_yes_probability,
        }
