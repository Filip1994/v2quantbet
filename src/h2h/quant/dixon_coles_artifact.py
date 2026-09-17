"""Canonical Dixon-Coles training fingerprints and JSON artifacts."""

from __future__ import annotations

import json
import platform
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any, Final

import numpy as np
import scipy

from h2h.domain.fixture_identity import API_FOOTBALL_PROVIDER
from h2h.domain.model_lifecycle import (
    DixonColesModelArtifact,
    DixonColesModelScope,
    DixonColesTrainingConfig,
    DixonColesTrainingProvenance,
    LoadedDixonColesModelVersion,
    _create_dixon_coles_model_artifact,
    _is_trusted_dixon_coles_model_artifact,
)
from h2h.quant.dixon_coles import DixonColesModel
from h2h.use_cases.api_football_training import (
    FT_SCORE_SEMANTIC,
    ApiFootballCompletedMatch,
    ApiFootballTrainingDataset,
    ApiFootballTrainingScope,
    _is_trusted_api_football_training_dataset,
)


ARTIFACT_SCHEMA: Final = "quantbet.dixon-coles-model"
ARTIFACT_SCHEMA_VERSION: Final = 2
ARTIFACT_MEDIA_TYPE: Final = "application/vnd.quantbet.dixon-coles+json"
TRAINING_DATASET_SCHEMA_VERSION: Final = 1
MODEL_IMPLEMENTATION_VERSION: Final = "quantbet.dixon-coles.v1"
NORMALIZATION_CONTRACT_VERSION: Final = "api-football-ft-v1"
MODEL_VERSION_PREFIX: Final = "dcm-json-v1:"
_CANDIDATE_AUTHORITY = object()


class ModelArtifactError(ValueError):
    """Base error for model artifact construction or loading."""


class ModelArtifactSerializationError(ModelArtifactError):
    pass


class ModelArtifactCorruptionError(ModelArtifactError):
    pass


class ModelArtifactIncompatibleError(ModelArtifactError):
    pass


@dataclass(frozen=True, slots=True, init=False)
class _TrustedDixonColesArtifactCandidate:
    provenance: DixonColesTrainingProvenance
    target_scope: DixonColesModelScope
    model: DixonColesModel
    python_version: str
    numpy_version: str
    scipy_version: str
    _authority: object

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("trusted model candidates are created only by training orchestration")


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ModelArtifactSerializationError("artifact timestamps must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ModelArtifactCorruptionError(f"{name} must be a timestamp string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ModelArtifactCorruptionError(f"{name} is not a canonical UTC timestamp") from exc
    return parsed


def _finite_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelArtifactSerializationError(f"{name} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ModelArtifactSerializationError(f"{name} must be finite")
    return result


def _float_hex(value: object, name: str) -> str:
    return _finite_float(value, name).hex()


def _parse_float_hex(value: object, name: str) -> float:
    if not isinstance(value, str):
        raise ModelArtifactCorruptionError(f"{name} must be a hexadecimal float string")
    try:
        result = float.fromhex(value)
    except ValueError as exc:
        raise ModelArtifactCorruptionError(f"{name} is malformed") from exc
    if not isfinite(result):
        raise ModelArtifactCorruptionError(f"{name} must be finite")
    return result


def _canonical_json(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ModelArtifactSerializationError("artifact is not canonical JSON") from exc
    return rendered.encode("utf-8")


def canonical_training_dataset_bytes(
    records: Sequence[ApiFootballCompletedMatch],
) -> bytes:
    canonical_records: list[dict[str, object]] = []
    ordered = sorted(records, key=lambda item: (item.date, item.provider_fixture_id))
    for record in ordered:
        if not isinstance(record, ApiFootballCompletedMatch):
            raise TypeError("training records must be ApiFootballCompletedMatch values")
        for name in (
            "provider_fixture_id",
            "home_id",
            "away_id",
            "home_goals",
            "away_goals",
            "league_id",
            "season",
        ):
            value = getattr(record, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        canonical_records.append(
            {
                "away_goals": record.away_goals,
                "away_team_id": record.away_id,
                "fixture_id": record.fixture_identity.fixture_id,
                "home_goals": record.home_goals,
                "home_team_id": record.home_id,
                "kickoff": _timestamp(record.date),
                "league_id": record.league_id,
                "provider_fixture_id": record.provider_fixture_id,
                "score_semantic": record.score_semantic,
                "season": record.season,
                "status": record.status,
            }
        )
    return _canonical_json(
        {
            "records": canonical_records,
            "training_dataset_schema_version": TRAINING_DATASET_SCHEMA_VERSION,
        }
    )


def api_football_training_dataset_sha256(
    records: Sequence[ApiFootballCompletedMatch],
) -> str:
    return sha256(canonical_training_dataset_bytes(records)).hexdigest()


def _runtime_versions() -> tuple[str, str, str]:
    return platform.python_version(), np.__version__, scipy.__version__


def training_input_fingerprint(
    *,
    scope: ApiFootballTrainingScope,
    config: DixonColesTrainingConfig,
    dataset_sha256: str,
    python_version: str,
    numpy_version: str,
    scipy_version: str,
) -> str:
    value = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "dataset_sha256": dataset_sha256,
        "league_id": scope.league_id,
        "min_matches": config.min_matches,
        "model_implementation_version": MODEL_IMPLEMENTATION_VERSION,
        "normalization_contract_version": NORMALIZATION_CONTRACT_VERSION,
        "numpy_version": numpy_version,
        "provider": API_FOOTBALL_PROVIDER,
        "python_version": python_version,
        "reference_time": _timestamp(config.reference_time),
        "ridge": _float_hex(config.ridge, "ridge"),
        "scipy_version": scipy_version,
        "season": scope.season,
        "team_id_namespace": API_FOOTBALL_PROVIDER,
        "trainer_code_version": config.trainer_code_version,
        "training_dataset_schema_version": TRAINING_DATASET_SCHEMA_VERSION,
        "training_end_at": _timestamp(scope.end_at),
        "training_start_at": _timestamp(scope.start_at),
        "xi": _float_hex(config.xi, "xi"),
    }
    return sha256(_canonical_json(value)).hexdigest()


def _trusted_candidate_from_training(
    *,
    dataset: ApiFootballTrainingDataset,
    scope: ApiFootballTrainingScope,
    config: DixonColesTrainingConfig,
    model: DixonColesModel,
    trained_at: datetime,
    target_scope: DixonColesModelScope | None = None,
) -> _TrustedDixonColesArtifactCandidate:
    if not _is_trusted_api_football_training_dataset(dataset):
        raise TypeError("dataset must come from trusted API-Football acquisition")
    if model.team_id_namespace != API_FOOTBALL_PROVIDER:
        raise ModelArtifactSerializationError("fitted model namespace is not api-football")
    resolved_target = target_scope or DixonColesModelScope(
        API_FOOTBALL_PROVIDER,
        API_FOOTBALL_PROVIDER,
        scope.league_id,
        scope.season,
    )
    if (
        resolved_target.provider != API_FOOTBALL_PROVIDER
        or resolved_target.team_id_namespace != API_FOOTBALL_PROVIDER
        or resolved_target.league_id != scope.league_id
    ):
        raise ModelArtifactSerializationError(
            "target scope must use the trusted provider, namespace, and training league"
        )
    records = dataset.records
    if not records:
        raise ModelArtifactSerializationError("trusted artifact requires accepted matches")
    if model.fitted_matches != len(records):
        raise ModelArtifactSerializationError("fitted matches must equal accepted matches")
    dataset_digest = api_football_training_dataset_sha256(records)
    python_version, numpy_version, scipy_version = _runtime_versions()
    input_fingerprint = training_input_fingerprint(
        scope=scope,
        config=config,
        dataset_sha256=dataset_digest,
        python_version=python_version,
        numpy_version=numpy_version,
        scipy_version=scipy_version,
    )
    counts: Counter[int] = DixonColesModel.team_match_counts(list(records))
    provenance = DixonColesTrainingProvenance(
        provider=API_FOOTBALL_PROVIDER,
        team_id_namespace=dataset.team_id_namespace,
        league_id=scope.league_id,
        season=scope.season,
        training_start_at=scope.start_at,
        training_end_at=scope.end_at,
        reference_time=config.reference_time,
        xi=config.xi,
        ridge=config.ridge,
        min_matches=config.min_matches,
        accepted_match_count=len(records),
        fitted_match_count=model.fitted_matches,
        earliest_match_at=records[0].date,
        latest_match_at=records[-1].date,
        team_count=len(model.team_ids),
        team_match_counts=tuple(sorted(counts.items())),
        dataset_sha256=dataset_digest,
        training_input_fingerprint=input_fingerprint,
        score_semantic=FT_SCORE_SEMANTIC,
        normalization_contract_version=NORMALIZATION_CONTRACT_VERSION,
        trained_at=trained_at,
        artifact_media_type=ARTIFACT_MEDIA_TYPE,
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        training_dataset_schema_version=TRAINING_DATASET_SCHEMA_VERSION,
        model_implementation_version=MODEL_IMPLEMENTATION_VERSION,
        trainer_code_version=config.trainer_code_version,
    )
    if tuple(sorted(counts)) != model.team_ids:
        raise ModelArtifactSerializationError("fitted team IDs do not match training records")
    candidate = object.__new__(_TrustedDixonColesArtifactCandidate)
    object.__setattr__(candidate, "provenance", provenance)
    object.__setattr__(candidate, "target_scope", resolved_target)
    object.__setattr__(candidate, "model", model)
    object.__setattr__(candidate, "python_version", python_version)
    object.__setattr__(candidate, "numpy_version", numpy_version)
    object.__setattr__(candidate, "scipy_version", scipy_version)
    object.__setattr__(candidate, "_authority", _CANDIDATE_AUTHORITY)
    return candidate


class DixonColesArtifactCodecV1:
    def encode(self, candidate: _TrustedDixonColesArtifactCandidate) -> DixonColesModelArtifact:
        if type(candidate) is not _TrustedDixonColesArtifactCandidate or (
            candidate._authority is not _CANDIDATE_AUTHORITY
        ):
            raise TypeError("artifact encoding requires a trusted training candidate")
        provenance = candidate.provenance
        model = candidate.model
        self._validate_model(model, provenance)
        payload = {
            "artifact_schema": ARTIFACT_SCHEMA,
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "fitted_state": {
                "attacks": [_float_hex(value, "attack") for value in model.attacks],
                "defenses": [_float_hex(value, "defense") for value in model.defenses],
                "fitted_matches": model.fitted_matches,
                "home_advantage": _float_hex(model.home_advantage, "home_advantage"),
                "intercept": _float_hex(model.intercept, "intercept"),
                "objective": _float_hex(model.objective, "objective"),
                "rho": _float_hex(model.rho, "rho"),
                "team_id_namespace": model.team_id_namespace,
                "team_ids": list(model.team_ids),
                "xi": _float_hex(model.xi, "xi"),
            },
            "model_implementation_version": MODEL_IMPLEMENTATION_VERSION,
            "provenance": self._provenance_payload(provenance),
            "runtime_versions": {
                "numpy": candidate.numpy_version,
                "python": candidate.python_version,
                "scipy": candidate.scipy_version,
            },
            "training_dataset_schema_version": TRAINING_DATASET_SCHEMA_VERSION,
            "target_scope": {
                "league_id": candidate.target_scope.league_id,
                "provider": candidate.target_scope.provider,
                "season": candidate.target_scope.season,
                "team_id_namespace": candidate.target_scope.team_id_namespace,
            },
        }
        artifact_bytes = _canonical_json(payload)
        digest = sha256(artifact_bytes).hexdigest()
        return _create_dixon_coles_model_artifact(
            model_version_id=MODEL_VERSION_PREFIX + digest,
            provenance=provenance,
            python_version=candidate.python_version,
            numpy_version=candidate.numpy_version,
            scipy_version=candidate.scipy_version,
            artifact_sha256=digest,
            artifact_bytes=artifact_bytes,
            target_scope=candidate.target_scope,
        )

    def decode(self, artifact: DixonColesModelArtifact) -> LoadedDixonColesModelVersion:
        if not _is_trusted_dixon_coles_model_artifact(artifact):
            raise TypeError("artifact must come from a trusted lifecycle boundary")
        digest = sha256(artifact.artifact_bytes).hexdigest()
        if digest != artifact.artifact_sha256:
            raise ModelArtifactCorruptionError("artifact digest mismatch")
        if artifact.model_version_id != MODEL_VERSION_PREFIX + digest:
            raise ModelArtifactCorruptionError("model version ID does not match artifact digest")
        try:
            payload = json.loads(artifact.artifact_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelArtifactCorruptionError("artifact is not valid UTF-8 JSON") from exc
        if not isinstance(payload, Mapping):
            raise ModelArtifactCorruptionError("artifact root must be an object")
        try:
            canonical_bytes = _canonical_json(payload)
        except ModelArtifactSerializationError as exc:
            raise ModelArtifactCorruptionError("artifact JSON contains invalid values") from exc
        if canonical_bytes != artifact.artifact_bytes:
            raise ModelArtifactCorruptionError("artifact JSON is not canonical")
        if payload.get("artifact_schema") != ARTIFACT_SCHEMA:
            raise ModelArtifactIncompatibleError("unsupported artifact schema")
        schema_version = payload.get("artifact_schema_version")
        if schema_version not in {1, ARTIFACT_SCHEMA_VERSION}:
            raise ModelArtifactIncompatibleError("unsupported artifact schema version")
        if payload.get("model_implementation_version") != MODEL_IMPLEMENTATION_VERSION:
            raise ModelArtifactIncompatibleError("unsupported model implementation version")
        if payload.get("training_dataset_schema_version") != TRAINING_DATASET_SCHEMA_VERSION:
            raise ModelArtifactIncompatibleError("unsupported training dataset schema version")
        provenance = self._parse_provenance(payload.get("provenance"))
        if (
            provenance.provider != API_FOOTBALL_PROVIDER
            or provenance.team_id_namespace != API_FOOTBALL_PROVIDER
        ):
            raise ModelArtifactCorruptionError("artifact provider and namespace must be api-football")
        if provenance.artifact_media_type != ARTIFACT_MEDIA_TYPE:
            raise ModelArtifactIncompatibleError("unsupported artifact media type")
        if provenance.artifact_schema_version != schema_version:
            raise ModelArtifactIncompatibleError("provenance artifact schema version is unsupported")
        if provenance.training_dataset_schema_version != TRAINING_DATASET_SCHEMA_VERSION:
            raise ModelArtifactIncompatibleError("provenance dataset schema version is unsupported")
        if provenance.model_implementation_version != MODEL_IMPLEMENTATION_VERSION:
            raise ModelArtifactIncompatibleError("provenance model implementation is unsupported")
        if provenance.normalization_contract_version != NORMALIZATION_CONTRACT_VERSION:
            raise ModelArtifactIncompatibleError("normalization contract version is unsupported")
        if provenance.score_semantic != FT_SCORE_SEMANTIC:
            raise ModelArtifactIncompatibleError("score semantic is unsupported")
        runtime = self._mapping(payload, "runtime_versions")
        state = self._mapping(payload, "fitted_state")
        target_scope = (
            provenance.scope
            if schema_version == 1
            else self._parse_target_scope(payload.get("target_scope"), provenance)
        )
        if target_scope != artifact.target_scope:
            raise ModelArtifactCorruptionError("artifact target scope contradicts stored metadata")
        if provenance != artifact.provenance:
            raise ModelArtifactCorruptionError("artifact provenance contradicts stored metadata")
        expected_runtime = {
            "python": artifact.python_version,
            "numpy": artifact.numpy_version,
            "scipy": artifact.scipy_version,
        }
        if dict(runtime) != expected_runtime:
            raise ModelArtifactCorruptionError("artifact runtime versions contradict metadata")
        model = self._parse_model(state, provenance)
        return LoadedDixonColesModelVersion(
            model_version_id=artifact.model_version_id,
            scope=artifact.scope,
            provenance=provenance,
            model=model,
        )

    @staticmethod
    def _parse_target_scope(
        value: object, provenance: DixonColesTrainingProvenance
    ) -> DixonColesModelScope:
        if not isinstance(value, Mapping):
            raise ModelArtifactCorruptionError("target_scope must be an object")
        try:
            scope = DixonColesModelScope(
                provider=value.get("provider"),  # type: ignore[arg-type]
                team_id_namespace=value.get("team_id_namespace"),  # type: ignore[arg-type]
                league_id=value.get("league_id"),  # type: ignore[arg-type]
                season=value.get("season"),  # type: ignore[arg-type]
            )
        except (TypeError, ValueError) as exc:
            raise ModelArtifactCorruptionError("invalid artifact target scope") from exc
        if (
            scope.provider != provenance.provider
            or scope.team_id_namespace != provenance.team_id_namespace
            or scope.league_id != provenance.league_id
        ):
            raise ModelArtifactCorruptionError(
                "target scope contradicts training provider, namespace, or league"
            )
        return scope

    @staticmethod
    def _provenance_payload(value: DixonColesTrainingProvenance) -> dict[str, object]:
        return {
            "accepted_match_count": value.accepted_match_count,
            "artifact_media_type": value.artifact_media_type,
            "artifact_schema_version": value.artifact_schema_version,
            "dataset_sha256": value.dataset_sha256,
            "earliest_match_at": _timestamp(value.earliest_match_at),
            "fitted_match_count": value.fitted_match_count,
            "latest_match_at": _timestamp(value.latest_match_at),
            "league_id": value.league_id,
            "min_matches": value.min_matches,
            "model_implementation_version": value.model_implementation_version,
            "normalization_contract_version": value.normalization_contract_version,
            "provider": value.provider,
            "reference_time": _timestamp(value.reference_time),
            "ridge": _float_hex(value.ridge, "ridge"),
            "score_semantic": value.score_semantic,
            "season": value.season,
            "team_count": value.team_count,
            "team_id_namespace": value.team_id_namespace,
            "team_match_counts": [
                {"match_count": count, "team_id": team_id}
                for team_id, count in value.team_match_counts
            ],
            "trained_at": _timestamp(value.trained_at),
            "trainer_code_version": value.trainer_code_version,
            "training_dataset_schema_version": value.training_dataset_schema_version,
            "training_end_at": _timestamp(value.training_end_at),
            "training_input_fingerprint": value.training_input_fingerprint,
            "training_start_at": _timestamp(value.training_start_at),
            "xi": _float_hex(value.xi, "xi"),
        }

    def _parse_provenance(self, value: object) -> DixonColesTrainingProvenance:
        if not isinstance(value, Mapping):
            raise ModelArtifactCorruptionError("provenance must be an object")
        counts = value.get("team_match_counts")
        if not isinstance(counts, list):
            raise ModelArtifactCorruptionError("team_match_counts must be an array")
        parsed_counts: list[tuple[int, int]] = []
        for item in counts:
            if not isinstance(item, Mapping):
                raise ModelArtifactCorruptionError("team_match_counts entries must be objects")
            parsed_counts.append((item.get("team_id"), item.get("match_count")))  # type: ignore[arg-type]
        try:
            return DixonColesTrainingProvenance(
                provider=value.get("provider"),  # type: ignore[arg-type]
                team_id_namespace=value.get("team_id_namespace"),  # type: ignore[arg-type]
                league_id=value.get("league_id"),  # type: ignore[arg-type]
                season=value.get("season"),  # type: ignore[arg-type]
                training_start_at=_parse_timestamp(value.get("training_start_at"), "training_start_at"),
                training_end_at=_parse_timestamp(value.get("training_end_at"), "training_end_at"),
                reference_time=_parse_timestamp(value.get("reference_time"), "reference_time"),
                xi=_parse_float_hex(value.get("xi"), "xi"),
                ridge=_parse_float_hex(value.get("ridge"), "ridge"),
                min_matches=value.get("min_matches"),  # type: ignore[arg-type]
                accepted_match_count=value.get("accepted_match_count"),  # type: ignore[arg-type]
                fitted_match_count=value.get("fitted_match_count"),  # type: ignore[arg-type]
                earliest_match_at=_parse_timestamp(value.get("earliest_match_at"), "earliest_match_at"),
                latest_match_at=_parse_timestamp(value.get("latest_match_at"), "latest_match_at"),
                team_count=value.get("team_count"),  # type: ignore[arg-type]
                team_match_counts=tuple(parsed_counts),
                dataset_sha256=value.get("dataset_sha256"),  # type: ignore[arg-type]
                training_input_fingerprint=value.get("training_input_fingerprint"),  # type: ignore[arg-type]
                score_semantic=value.get("score_semantic"),  # type: ignore[arg-type]
                normalization_contract_version=value.get("normalization_contract_version"),  # type: ignore[arg-type]
                trained_at=_parse_timestamp(value.get("trained_at"), "trained_at"),
                artifact_media_type=value.get("artifact_media_type"),  # type: ignore[arg-type]
                artifact_schema_version=value.get("artifact_schema_version"),  # type: ignore[arg-type]
                training_dataset_schema_version=value.get("training_dataset_schema_version"),  # type: ignore[arg-type]
                model_implementation_version=value.get("model_implementation_version"),  # type: ignore[arg-type]
                trainer_code_version=value.get("trainer_code_version"),  # type: ignore[arg-type]
            )
        except (TypeError, ValueError) as exc:
            raise ModelArtifactCorruptionError("invalid artifact provenance") from exc

    def _parse_model(
        self, state: Mapping[str, Any], provenance: DixonColesTrainingProvenance
    ) -> DixonColesModel:
        team_ids_raw = state.get("team_ids")
        attacks_raw = state.get("attacks")
        defenses_raw = state.get("defenses")
        if not isinstance(team_ids_raw, list) or not isinstance(attacks_raw, list) or not isinstance(defenses_raw, list):
            raise ModelArtifactCorruptionError("team IDs and parameter vectors must be arrays")
        team_ids = tuple(team_ids_raw)
        for value in team_ids:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ModelArtifactCorruptionError("team IDs must be positive integers")
        if len(team_ids) < 4 or tuple(sorted(set(team_ids))) != team_ids:
            raise ModelArtifactCorruptionError("team IDs must be unique and deterministically ordered")
        if len(attacks_raw) != len(team_ids) or len(defenses_raw) != len(team_ids):
            raise ModelArtifactCorruptionError("parameter vectors must align with team IDs")
        attacks = np.asarray(
            [_parse_float_hex(value, "attack") for value in attacks_raw], dtype=float
        ).copy()
        defenses = np.asarray(
            [_parse_float_hex(value, "defense") for value in defenses_raw], dtype=float
        ).copy()
        intercept = _parse_float_hex(state.get("intercept"), "intercept")
        home_advantage = _parse_float_hex(state.get("home_advantage"), "home_advantage")
        rho = _parse_float_hex(state.get("rho"), "rho")
        xi = _parse_float_hex(state.get("xi"), "xi")
        objective = _parse_float_hex(state.get("objective"), "objective")
        fitted_matches = state.get("fitted_matches")
        namespace = state.get("team_id_namespace")
        if isinstance(fitted_matches, bool) or not isinstance(fitted_matches, int):
            raise ModelArtifactCorruptionError("fitted_matches must be an integer")
        if not isinstance(namespace, str):
            raise ModelArtifactCorruptionError("team_id_namespace must be a string")
        if not -2.0 <= intercept <= 2.0:
            raise ModelArtifactCorruptionError("intercept is outside supported bounds")
        if not -1.0 <= home_advantage <= 1.0:
            raise ModelArtifactCorruptionError("home advantage is outside supported bounds")
        if not -0.2 <= rho <= 0.2:
            raise ModelArtifactCorruptionError("rho is outside supported bounds")
        if xi < 0.0 or xi != provenance.xi:
            raise ModelArtifactCorruptionError("artifact xi contradicts provenance")
        if fitted_matches != provenance.fitted_match_count:
            raise ModelArtifactCorruptionError("fitted match count contradicts provenance")
        if namespace != provenance.team_id_namespace:
            raise ModelArtifactCorruptionError("fitted namespace contradicts provenance")
        if tuple(team_id for team_id, _ in provenance.team_match_counts) != team_ids:
            raise ModelArtifactCorruptionError("fitted team IDs contradict provenance")
        attacks.setflags(write=False)
        defenses.setflags(write=False)
        return DixonColesModel(
            team_ids=team_ids,
            team_id_namespace=namespace,
            attacks=attacks,
            defenses=defenses,
            intercept=intercept,
            home_advantage=home_advantage,
            rho=rho,
            xi=xi,
            fitted_matches=fitted_matches,
            objective=objective,
        )

    @staticmethod
    def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        nested = value.get(key)
        if not isinstance(nested, Mapping):
            raise ModelArtifactCorruptionError(f"{key} must be an object")
        return nested

    @staticmethod
    def _validate_model(
        model: DixonColesModel, provenance: DixonColesTrainingProvenance
    ) -> None:
        if not isinstance(model, DixonColesModel):
            raise TypeError("model must be a DixonColesModel")
        if model.team_id_namespace != API_FOOTBALL_PROVIDER:
            raise ModelArtifactSerializationError("model namespace must be api-football")
        if tuple(sorted(set(model.team_ids))) != model.team_ids or len(model.team_ids) < 4:
            raise ModelArtifactSerializationError("model team IDs are invalid")
        if len(model.attacks) != len(model.team_ids) or len(model.defenses) != len(model.team_ids):
            raise ModelArtifactSerializationError("model parameter vectors are misaligned")
        for name, value in (
            ("intercept", model.intercept),
            ("home_advantage", model.home_advantage),
            ("rho", model.rho),
            ("xi", model.xi),
            ("objective", model.objective),
        ):
            _finite_float(value, name)
        for value in (*model.attacks, *model.defenses):
            _finite_float(value, "model parameter")
        if not -2.0 <= model.intercept <= 2.0:
            raise ModelArtifactSerializationError("intercept is outside supported bounds")
        if not -1.0 <= model.home_advantage <= 1.0:
            raise ModelArtifactSerializationError("home advantage is outside supported bounds")
        if not -0.2 <= model.rho <= 0.2:
            raise ModelArtifactSerializationError("rho is outside supported bounds")
        if model.xi < 0.0 or model.xi != provenance.xi:
            raise ModelArtifactSerializationError("model xi contradicts provenance")
        if model.fitted_matches != provenance.fitted_match_count:
            raise ModelArtifactSerializationError("model fitted count contradicts provenance")


def _provenance_from_artifact_bytes(artifact_bytes: bytes) -> DixonColesTrainingProvenance:
    """Decode only protected provenance for PostgreSQL metadata comparison."""
    try:
        payload = json.loads(artifact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelArtifactCorruptionError("artifact is not valid UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise ModelArtifactCorruptionError("artifact root must be an object")
    return DixonColesArtifactCodecV1()._parse_provenance(payload.get("provenance"))


def _target_scope_from_artifact_bytes(artifact_bytes: bytes) -> DixonColesModelScope:
    """Decode the explicit prediction target scope, with V1 compatibility."""
    try:
        payload = json.loads(artifact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelArtifactCorruptionError("artifact is not valid UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise ModelArtifactCorruptionError("artifact root must be an object")
    codec = DixonColesArtifactCodecV1()
    provenance = codec._parse_provenance(payload.get("provenance"))
    if payload.get("artifact_schema_version") == 1:
        return provenance.scope
    return codec._parse_target_scope(payload.get("target_scope"), provenance)
