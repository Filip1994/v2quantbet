from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import patch

import numpy as np
import pytest

from h2h.application import build_trusted_api_football_historical_results
from h2h.config import ApplicationSettings
from h2h.domain.fixture_identity import api_football_fixture_identity
from h2h.domain.model_lifecycle import DixonColesTrainingConfig
from h2h.domain.model_lifecycle import _create_dixon_coles_model_artifact
from h2h.odds.http import UrllibJsonTransport
from h2h.quant.dixon_coles_artifact import (
    ARTIFACT_SCHEMA_VERSION,
    MODEL_VERSION_PREFIX,
    DixonColesArtifactCodecV1,
    ModelArtifactCorruptionError,
    ModelArtifactIncompatibleError,
    ModelArtifactSerializationError,
    _TrustedDixonColesArtifactCandidate,
    _trusted_candidate_from_training,
    api_football_training_dataset_sha256,
    canonical_training_dataset_bytes,
)
from h2h.use_cases.api_football_training import (
    FT_SCORE_SEMANTIC,
    ApiFootballCompletedMatch,
    ApiFootballTrainingScope,
    fit_api_football_dixon_coles,
)


START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 2, 1, tzinfo=UTC)
TRAINED_AT = datetime(2025, 2, 2, tzinfo=UTC)


def record(fixture_id=101, date=START, home=1, away=2, hg=2, ag=1):
    return ApiFootballCompletedMatch(
        fixture_identity=api_football_fixture_identity(fixture_id),
        date=date,
        home_id=home,
        away_id=away,
        home_goals=hg,
        away_goals=ag,
        league_id=39,
        season=2024,
        status="FT",
        score_semantic=FT_SCORE_SEMANTIC,
    )


def test_dataset_fingerprint_has_fixed_golden_vector_and_order() -> None:
    records = [
        record(102, START + timedelta(days=1), 2, 1, 0, 0),
        record(101, START, 1, 2, 2, 1),
    ]
    assert api_football_training_dataset_sha256(records) == (
        "26855b88778a55a012313fc5f8ac52704050ed8d37099359acf42f40e371a1af"
    )
    assert canonical_training_dataset_bytes(records) == canonical_training_dataset_bytes(
        tuple(reversed(records))
    )


@pytest.mark.parametrize(
    "changed",
    [
        record(999),
        record(home=2, away=1),
        record(hg=1),
        record(date=START + timedelta(seconds=1)),
        replace(record(), score_semantic="changed"),
    ],
)
def test_dataset_digest_changes_for_identity_score_time_and_semantic(changed) -> None:
    assert api_football_training_dataset_sha256([changed]) != api_football_training_dataset_sha256(
        [record()]
    )


def _payload():
    response = []
    teams = (1, 2, 3, 4)
    for index in range(24):
        home = teams[index % 4]
        away = teams[(index + 1 + index // 4) % 4]
        if home == away:
            away = teams[(teams.index(away) + 1) % 4]
        match = record(
            1000 + index,
            START + timedelta(days=index),
            home,
            away,
            index % 3,
            (index + 1) % 2,
        )
        response.append(
            {
                "fixture": {
                    "id": match.provider_fixture_id,
                    "date": match.date.isoformat(),
                    "status": {"short": "FT"},
                },
                "league": {"id": 39, "season": 2024},
                "teams": {"home": {"id": home}, "away": {"id": away}},
                "goals": {"home": match.home_goals, "away": match.away_goals},
                "score": {
                    "fulltime": {"home": match.home_goals, "away": match.away_goals},
                    "extratime": {"home": None, "away": None},
                    "penalty": {"home": None, "away": None},
                },
            }
        )
    return {"errors": [], "results": len(response), "paging": {"current": 1, "total": 1}, "response": response}


def trusted_artifact(trained_at=TRAINED_AT):
    settings = ApplicationSettings(database_path="unused.sqlite3", api_football_key="secret")
    with patch.object(UrllibJsonTransport, "get_json", return_value=_payload()):
        dataset = build_trusted_api_football_historical_results(settings).acquire(
            ApiFootballTrainingScope(39, 2024, START, END)
        )
    config = DixonColesTrainingConfig(
        END,
        0.001,
        min_matches=20,
        trainer_code_version="test-build",
    )
    model = fit_api_football_dixon_coles(
        dataset,
        reference_time=config.reference_time,
        xi=config.xi,
        ridge=config.ridge,
        min_matches=config.min_matches,
    )
    candidate = _trusted_candidate_from_training(
        dataset=dataset,
        scope=ApiFootballTrainingScope(39, 2024, START, END),
        config=config,
        model=model,
        trained_at=trained_at,
    )
    return model, DixonColesArtifactCodecV1().encode(candidate)


def test_artifact_is_deterministic_and_exact_float_round_trip() -> None:
    original, artifact = trusted_artifact()
    second = DixonColesArtifactCodecV1().encode(
        _candidate_from_existing(original, artifact)
    )
    assert second.artifact_bytes == artifact.artifact_bytes
    assert second.model_version_id == artifact.model_version_id
    loaded = DixonColesArtifactCodecV1().decode(artifact)
    assert loaded.model_version_id == artifact.model_version_id
    assert loaded.model.intercept.hex() == original.intercept.hex()
    assert loaded.model.home_advantage.hex() == original.home_advantage.hex()
    assert loaded.model.rho.hex() == original.rho.hex()
    assert [value.hex() for value in loaded.model.attacks] == [
        float(value).hex() for value in original.attacks
    ]
    assert not loaded.model.attacks.flags.writeable
    assert not loaded.model.defenses.flags.writeable
    np.testing.assert_allclose(
        tuple(loaded.model.market_probabilities(1, 2).values()),
        tuple(original.market_probabilities(1, 2).values()),
        rtol=0.0,
        atol=0.0,
    )


def test_identical_training_inputs_have_separate_version_and_input_identities() -> None:
    _, first = trusted_artifact(TRAINED_AT)
    _, second = trusted_artifact(TRAINED_AT + timedelta(microseconds=1))
    assert first.provenance.training_input_fingerprint == (
        second.provenance.training_input_fingerprint
    )
    assert first.model_version_id != second.model_version_id


def _candidate_from_existing(model, artifact):
    candidate = object.__new__(_TrustedDixonColesArtifactCandidate)
    object.__setattr__(candidate, "provenance", artifact.provenance)
    object.__setattr__(candidate, "model", model)
    object.__setattr__(candidate, "python_version", artifact.python_version)
    object.__setattr__(candidate, "numpy_version", artifact.numpy_version)
    object.__setattr__(candidate, "scipy_version", artifact.scipy_version)
    from h2h.quant import dixon_coles_artifact as module

    object.__setattr__(candidate, "_authority", module._CANDIDATE_AUTHORITY)
    return candidate


def _rewrite_artifact(artifact, mutate):
    payload = json.loads(artifact.artifact_bytes)
    mutate(payload)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = sha256(raw).hexdigest()
    return _create_dixon_coles_model_artifact(
        model_version_id=MODEL_VERSION_PREFIX + digest,
        provenance=artifact.provenance,
        python_version=artifact.python_version,
        numpy_version=artifact.numpy_version,
        scipy_version=artifact.scipy_version,
        artifact_sha256=digest,
        artifact_bytes=raw,
    )


def test_unsupported_schema_and_implementation_fail_closed() -> None:
    _, artifact = trusted_artifact()
    unsupported_schema = _rewrite_artifact(
        artifact, lambda payload: payload.update(artifact_schema_version=ARTIFACT_SCHEMA_VERSION + 1)
    )
    with pytest.raises(ModelArtifactIncompatibleError, match="schema version"):
        DixonColesArtifactCodecV1().decode(unsupported_schema)
    unsupported_model = _rewrite_artifact(
        artifact, lambda payload: payload.update(model_implementation_version="future")
    )
    with pytest.raises(ModelArtifactIncompatibleError, match="implementation"):
        DixonColesArtifactCodecV1().decode(unsupported_model)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other-provider"),
        ("team_id_namespace", "other-namespace"),
        ("league_id", 40),
        ("season", 2025),
        ("reference_time", END + timedelta(seconds=1)),
    ],
)
def test_stored_metadata_cannot_contradict_canonical_artifact(field, value) -> None:
    _, artifact = trusted_artifact()
    contradictory = _create_dixon_coles_model_artifact(
        model_version_id=artifact.model_version_id,
        provenance=replace(artifact.provenance, **{field: value}),
        python_version=artifact.python_version,
        numpy_version=artifact.numpy_version,
        scipy_version=artifact.scipy_version,
        artifact_sha256=artifact.artifact_sha256,
        artifact_bytes=artifact.artifact_bytes,
    )
    with pytest.raises(ModelArtifactCorruptionError, match="contradicts stored metadata"):
        DixonColesArtifactCodecV1().decode(contradictory)


def test_corruption_malformed_vectors_and_nonfinite_state_fail_closed() -> None:
    _, artifact = trusted_artifact()
    corrupt = _create_dixon_coles_model_artifact(
        model_version_id=artifact.model_version_id,
        provenance=artifact.provenance,
        python_version=artifact.python_version,
        numpy_version=artifact.numpy_version,
        scipy_version=artifact.scipy_version,
        artifact_sha256=artifact.artifact_sha256,
        artifact_bytes=artifact.artifact_bytes + b"x",
    )
    with pytest.raises(ModelArtifactCorruptionError, match="digest"):
        DixonColesArtifactCodecV1().decode(corrupt)
    duplicate_team = _rewrite_artifact(
        artifact, lambda payload: payload["fitted_state"]["team_ids"].__setitem__(1, 1)
    )
    with pytest.raises(ModelArtifactCorruptionError, match="team IDs"):
        DixonColesArtifactCodecV1().decode(duplicate_team)
    bad_length = _rewrite_artifact(
        artifact, lambda payload: payload["fitted_state"]["attacks"].pop()
    )
    with pytest.raises(ModelArtifactCorruptionError, match="align"):
        DixonColesArtifactCodecV1().decode(bad_length)
    nonfinite = _rewrite_artifact(
        artifact, lambda payload: payload["fitted_state"].update(rho="inf")
    )
    with pytest.raises(ModelArtifactCorruptionError, match="finite"):
        DixonColesArtifactCodecV1().decode(nonfinite)

    malformed_bytes = b'{"artifact_schema":'
    malformed_digest = sha256(malformed_bytes).hexdigest()
    malformed = _create_dixon_coles_model_artifact(
        model_version_id=MODEL_VERSION_PREFIX + malformed_digest,
        provenance=artifact.provenance,
        python_version=artifact.python_version,
        numpy_version=artifact.numpy_version,
        scipy_version=artifact.scipy_version,
        artifact_sha256=malformed_digest,
        artifact_bytes=malformed_bytes,
    )
    with pytest.raises(ModelArtifactCorruptionError, match="valid UTF-8 JSON"):
        DixonColesArtifactCodecV1().decode(malformed)


def test_bare_model_and_caller_candidate_cannot_mint_artifact() -> None:
    model, _ = trusted_artifact()
    with pytest.raises(TypeError, match="training orchestration"):
        _TrustedDixonColesArtifactCandidate()
    with pytest.raises(TypeError, match="trusted training candidate"):
        DixonColesArtifactCodecV1().encode(model)  # type: ignore[arg-type]


def test_encoder_rejects_nonfinite_model_state() -> None:
    model, artifact = trusted_artifact()
    model.objective = float("nan")
    with pytest.raises(ModelArtifactSerializationError, match="objective"):
        DixonColesArtifactCodecV1().encode(_candidate_from_existing(model, artifact))
