"""Immutable Dixon-Coles model lifecycle domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from h2h.quant.dixon_coles import DixonColesModel


_ARTIFACT_AUTHORITY = object()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be expressed in UTC")
    return value.astimezone(UTC)


def _nonnegative_finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


@dataclass(frozen=True, slots=True)
class DixonColesModelScope:
    provider: str
    team_id_namespace: str
    league_id: int
    season: int

    def __post_init__(self) -> None:
        _text(self.provider, "provider")
        _text(self.team_id_namespace, "team_id_namespace")
        _positive_int(self.league_id, "league_id")
        _positive_int(self.season, "season")


@dataclass(frozen=True, slots=True)
class DixonColesTrainingConfig:
    reference_time: datetime
    xi: float
    ridge: float = 0.01
    min_matches: int = 80
    trainer_code_version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference_time", _utc(self.reference_time, "reference_time"))
        object.__setattr__(self, "xi", _nonnegative_finite(self.xi, "xi"))
        object.__setattr__(self, "ridge", _nonnegative_finite(self.ridge, "ridge"))
        _positive_int(self.min_matches, "min_matches")
        _text(self.trainer_code_version, "trainer_code_version")


@dataclass(frozen=True, slots=True)
class DixonColesTrainingProvenance:
    provider: str
    team_id_namespace: str
    league_id: int
    season: int
    training_start_at: datetime
    training_end_at: datetime
    reference_time: datetime
    xi: float
    ridge: float
    min_matches: int
    accepted_match_count: int
    fitted_match_count: int
    earliest_match_at: datetime
    latest_match_at: datetime
    team_count: int
    team_match_counts: tuple[tuple[int, int], ...]
    dataset_sha256: str
    training_input_fingerprint: str
    score_semantic: str
    normalization_contract_version: str
    trained_at: datetime
    artifact_media_type: str
    artifact_schema_version: int
    training_dataset_schema_version: int
    model_implementation_version: str
    trainer_code_version: str

    def __post_init__(self) -> None:
        _text(self.provider, "provider")
        _text(self.team_id_namespace, "team_id_namespace")
        _positive_int(self.league_id, "league_id")
        _positive_int(self.season, "season")
        start = _utc(self.training_start_at, "training_start_at")
        end = _utc(self.training_end_at, "training_end_at")
        reference = _utc(self.reference_time, "reference_time")
        earliest = _utc(self.earliest_match_at, "earliest_match_at")
        latest = _utc(self.latest_match_at, "latest_match_at")
        trained = _utc(self.trained_at, "trained_at")
        if not start < end:
            raise ValueError("training_start_at must be before training_end_at")
        if reference < end:
            raise ValueError("reference_time must be at or after training_end_at")
        if not start <= earliest <= latest < end:
            raise ValueError("accepted match timestamps must lie inside the training scope")
        object.__setattr__(self, "training_start_at", start)
        object.__setattr__(self, "training_end_at", end)
        object.__setattr__(self, "reference_time", reference)
        object.__setattr__(self, "earliest_match_at", earliest)
        object.__setattr__(self, "latest_match_at", latest)
        object.__setattr__(self, "trained_at", trained)
        object.__setattr__(self, "xi", _nonnegative_finite(self.xi, "xi"))
        object.__setattr__(self, "ridge", _nonnegative_finite(self.ridge, "ridge"))
        _positive_int(self.min_matches, "min_matches")
        _positive_int(self.accepted_match_count, "accepted_match_count")
        _positive_int(self.fitted_match_count, "fitted_match_count")
        _positive_int(self.team_count, "team_count")
        if self.accepted_match_count != self.fitted_match_count:
            raise ValueError("accepted_match_count must equal fitted_match_count")
        if self.accepted_match_count < self.min_matches:
            raise ValueError("accepted_match_count must satisfy min_matches")
        normalized_counts = tuple(self.team_match_counts)
        if len(normalized_counts) != self.team_count:
            raise ValueError("team_match_counts length must equal team_count")
        previous = 0
        for team_id, count in normalized_counts:
            _positive_int(team_id, "team_match_counts team_id")
            _positive_int(count, "team_match_counts count")
            if team_id <= previous:
                raise ValueError("team_match_counts must be ordered by unique team ID")
            previous = team_id
        if sum(count for _, count in normalized_counts) != 2 * self.accepted_match_count:
            raise ValueError("team_match_counts must account for both teams in every match")
        object.__setattr__(self, "team_match_counts", normalized_counts)
        for name in ("dataset_sha256", "training_input_fingerprint"):
            digest = getattr(self, name)
            if not isinstance(digest, str) or len(digest) != 64 or any(
                char not in "0123456789abcdef" for char in digest
            ):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        for name in (
            "score_semantic",
            "normalization_contract_version",
            "artifact_media_type",
            "model_implementation_version",
            "trainer_code_version",
        ):
            _text(getattr(self, name), name)
        _positive_int(self.artifact_schema_version, "artifact_schema_version")
        _positive_int(self.training_dataset_schema_version, "training_dataset_schema_version")

    @property
    def scope(self) -> DixonColesModelScope:
        return DixonColesModelScope(
            self.provider,
            self.team_id_namespace,
            self.league_id,
            self.season,
        )


@dataclass(frozen=True, slots=True, init=False)
class DixonColesModelArtifact:
    model_version_id: str
    provenance: DixonColesTrainingProvenance
    python_version: str
    numpy_version: str
    scipy_version: str
    artifact_sha256: str
    artifact_bytes: bytes
    target_scope: DixonColesModelScope
    _authority: object

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("model artifacts are created only by trusted lifecycle boundaries")

    @property
    def scope(self) -> DixonColesModelScope:
        return self.target_scope


def _create_dixon_coles_model_artifact(
    *,
    model_version_id: str,
    provenance: DixonColesTrainingProvenance,
    python_version: str,
    numpy_version: str,
    scipy_version: str,
    artifact_sha256: str,
    artifact_bytes: bytes,
    target_scope: DixonColesModelScope | None = None,
) -> DixonColesModelArtifact:
    artifact = object.__new__(DixonColesModelArtifact)
    for name, value in (
        ("model_version_id", model_version_id),
        ("provenance", provenance),
        ("python_version", python_version),
        ("numpy_version", numpy_version),
        ("scipy_version", scipy_version),
        ("artifact_sha256", artifact_sha256),
        ("artifact_bytes", bytes(artifact_bytes)),
        ("target_scope", target_scope or provenance.scope),
        ("_authority", _ARTIFACT_AUTHORITY),
    ):
        object.__setattr__(artifact, name, value)
    return artifact


def _is_trusted_dixon_coles_model_artifact(value: object) -> bool:
    return type(value) is DixonColesModelArtifact and value._authority is _ARTIFACT_AUTHORITY


@dataclass(frozen=True, slots=True)
class DixonColesModelVersion:
    artifact: DixonColesModelArtifact
    persisted_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "persisted_at", _utc(self.persisted_at, "persisted_at"))

    @property
    def model_version_id(self) -> str:
        return self.artifact.model_version_id

    @property
    def scope(self) -> DixonColesModelScope:
        return self.artifact.scope


@dataclass(frozen=True, slots=True)
class ActiveDixonColesModel:
    scope: DixonColesModelScope
    model_version_id: str
    activated_at: datetime
    generation: int

    def __post_init__(self) -> None:
        _text(self.model_version_id, "model_version_id")
        object.__setattr__(self, "activated_at", _utc(self.activated_at, "activated_at"))
        _positive_int(self.generation, "generation")


@dataclass(frozen=True, slots=True)
class LoadedDixonColesModelVersion:
    model_version_id: str
    scope: DixonColesModelScope
    provenance: DixonColesTrainingProvenance
    model: DixonColesModel


@dataclass(frozen=True, slots=True)
class ValidatedActiveDixonColesModel:
    """Validated artifact plus the exact active-pointer state that selected it."""

    loaded: LoadedDixonColesModelVersion
    generation: int
    activated_at: datetime

    def __post_init__(self) -> None:
        _positive_int(self.generation, "generation")
        object.__setattr__(self, "activated_at", _utc(self.activated_at, "activated_at"))

    @property
    def model_version_id(self) -> str:
        return self.loaded.model_version_id

    @property
    def scope(self) -> DixonColesModelScope:
        return self.loaded.scope
