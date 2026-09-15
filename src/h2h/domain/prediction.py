"""Read-only interfaces and internal implementations for fixture-bound predictions."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from types import MappingProxyType
from typing import Protocol

from .fixture import Fixture
from .fixture_identity import ProviderFixtureReference, ResolvedFixtureIdentity


class PredictionTarget(Protocol):
    """Public read-only view of an authoritative prediction target."""

    @property
    def fixture_identity(self) -> ResolvedFixtureIdentity: ...

    @property
    def fixture_id(self) -> str: ...

    @property
    def home_team_id(self) -> int: ...

    @property
    def away_team_id(self) -> int: ...

    @property
    def team_id_namespace(self) -> str: ...


class FixturePrediction(Protocol):
    """Public read-only view of a prediction produced by the trusted predictor."""

    @property
    def target(self) -> PredictionTarget: ...

    @property
    def probabilities(self) -> Mapping[str, float]: ...


@dataclass(frozen=True, slots=True, init=False)
class _PredictionTarget:
    """Concrete target created only from an authoritative fixture."""

    fixture_identity: ResolvedFixtureIdentity
    home_team_id: int
    away_team_id: int

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("prediction targets are created by the fixture predictor")

    @property
    def fixture_id(self) -> str:
        return self.fixture_identity.fixture_id

    @property
    def team_id_namespace(self) -> str:
        return self.fixture_identity.provider_reference.provider


@dataclass(frozen=True, slots=True, init=False)
class _FixturePrediction:
    """Concrete provenance-valid result created only after model execution."""

    target: _PredictionTarget
    probabilities: Mapping[str, float]

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("fixture predictions are created by the fixture predictor")


def _prediction_target_from_fixture(fixture: Fixture) -> _PredictionTarget:
    """Create the internal target from one authoritative fixture."""
    if not isinstance(fixture, Fixture):
        raise TypeError("fixture must be a Fixture")
    if fixture.provider_fixture_id is None:
        raise ValueError("fixture.provider_fixture_id is required")
    if fixture.provider_home_team_id is None:
        raise ValueError("fixture.provider_home_team_id is required")
    if fixture.provider_away_team_id is None:
        raise ValueError("fixture.provider_away_team_id is required")
    if fixture.provider_home_team_id == fixture.provider_away_team_id:
        raise ValueError("provider home and away team IDs must be different")

    fixture_identity = ResolvedFixtureIdentity(
        fixture_id=fixture.fixture_id,
        provider_reference=ProviderFixtureReference(
            provider=fixture.provider,
            provider_fixture_id=fixture.provider_fixture_id,
        ),
    )
    target = object.__new__(_PredictionTarget)
    object.__setattr__(target, "fixture_identity", fixture_identity)
    object.__setattr__(target, "home_team_id", fixture.provider_home_team_id)
    object.__setattr__(target, "away_team_id", fixture.provider_away_team_id)
    return target


def _fixture_prediction_from_execution(
    *,
    target: _PredictionTarget,
    probabilities: Mapping[str, float],
) -> _FixturePrediction:
    """Bind validated model output to the exact internal execution target."""
    if type(target) is not _PredictionTarget:
        raise TypeError("target must be the predictor's execution target")
    if not isinstance(probabilities, Mapping):
        raise TypeError("probabilities must be a mapping")

    expected_keys = {"OVER_2_5", "UNDER_2_5", "BTTS_YES"}
    copied = dict(probabilities)
    if set(copied) != expected_keys:
        raise ValueError(
            "probabilities must contain exactly OVER_2_5, UNDER_2_5, and BTTS_YES"
        )
    normalized: dict[str, float] = {}
    for key, value in copied.items():
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"{key} must be a real numeric scalar")
        probability = float(value)
        if not isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError(f"{key} must be finite and between 0 and 1")
        normalized[key] = probability

    prediction = object.__new__(_FixturePrediction)
    object.__setattr__(prediction, "target", target)
    object.__setattr__(prediction, "probabilities", MappingProxyType(normalized))
    return prediction


def _is_fixture_prediction(value: object) -> bool:
    """Return whether ``value`` is the concrete trusted prediction result."""
    return type(value) is _FixturePrediction
