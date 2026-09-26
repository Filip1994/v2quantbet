"""CornerLab V2 pressure-statistics Poisson model.

The model is structural: bookmaker prices are not model features. Historical match
statistics are consumed in kickoff order so each training row uses only earlier matches.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import exp, floor, isfinite, log
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson


FEATURE_VERSION = "CORNER_PRESSURE_FEATURES_V1"
MODEL_NAME = "Corner pressure Poisson GLM"
MODEL_PREFIX = "CORNER_PRESSURE_POISSON_V1:"
RIDGE_PENALTY = 2.0
MIN_TEAM_HISTORY = 3
MIN_TRAINING_EXAMPLES = 80
HISTORY_LIMIT = 6000

_BASE_METRICS = (
    "corners_for",
    "corners_against",
    "possession",
    "shots_for",
    "shots_against",
    "sot_for",
    "sot_against",
    "blocked_for",
    "inside_box_for",
    "offsides_for",
    "accurate_passes_for",
    "pass_accuracy",
)
_LONG_METRICS = (
    "corners_for",
    "corners_against",
    "possession",
    "shots_for",
    "sot_for",
)
_VENUE_METRICS = (
    "corners_for",
    "corners_against",
    "possession",
    "shots_for",
    "sot_for",
    "inside_box_for",
    "accurate_passes_for",
)


def _feature_names() -> tuple[str, ...]:
    names: list[str] = []
    for side in ("home", "away"):
        names.extend(f"{side}_l5_{metric}" for metric in _BASE_METRICS)
        names.extend(f"{side}_l10_{metric}" for metric in _LONG_METRICS)
        names.extend(f"{side}_venue_l5_{metric}" for metric in _VENUE_METRICS)
    return tuple(names)


FEATURE_NAMES = _feature_names()


@dataclass(frozen=True, slots=True)
class TeamMatchSample:
    venue: str
    values: dict[str, float | None]


@dataclass(frozen=True, slots=True)
class CornerModelArtifact:
    model_version: str
    trained_at: datetime
    training_cutoff: datetime
    feature_version: str
    training_sample_size: int
    history_match_count: int
    ridge_penalty: float
    coefficients: dict[str, float]
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    training_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CornerFeatureSnapshot:
    fixture_id: str
    decision_at: datetime
    model_version: str
    expected_total_corners: float
    home_history_size: int
    away_history_size: int
    feature_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CornerEstimate:
    expected_total_corners: float
    model: CornerModelArtifact
    snapshot: CornerFeatureSnapshot

    def probability(self, selection: str, line: float) -> float:
        threshold = floor(line)
        under = float(poisson.cdf(threshold, self.expected_total_corners))
        if selection == "UNDER":
            return under
        if selection == "OVER":
            return 1.0 - under
        raise ValueError("selection must be OVER or UNDER")


@dataclass(frozen=True, slots=True)
class CornerEstimateResult:
    estimate: CornerEstimate | None
    reason: str
    details: dict[str, Any]


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _team_samples(row: dict[str, Any]) -> tuple[TeamMatchSample, TeamMatchSample]:
    home = TeamMatchSample(
        venue="HOME",
        values={
            "corners_for": _number(row.get("home_corner_kicks")),
            "corners_against": _number(row.get("away_corner_kicks")),
            "possession": _number(row.get("home_ball_possession")),
            "shots_for": _number(row.get("home_total_shots")),
            "shots_against": _number(row.get("away_total_shots")),
            "sot_for": _number(row.get("home_shots_on_goal")),
            "sot_against": _number(row.get("away_shots_on_goal")),
            "blocked_for": _number(row.get("home_blocked_shots")),
            "inside_box_for": _number(row.get("home_shots_insidebox")),
            "offsides_for": _number(row.get("home_offsides")),
            "accurate_passes_for": _number(row.get("home_passes_accurate")),
            "pass_accuracy": _number(row.get("home_pass_accuracy")),
        },
    )
    away = TeamMatchSample(
        venue="AWAY",
        values={
            "corners_for": _number(row.get("away_corner_kicks")),
            "corners_against": _number(row.get("home_corner_kicks")),
            "possession": _number(row.get("away_ball_possession")),
            "shots_for": _number(row.get("away_total_shots")),
            "shots_against": _number(row.get("home_total_shots")),
            "sot_for": _number(row.get("away_shots_on_goal")),
            "sot_against": _number(row.get("home_shots_on_goal")),
            "blocked_for": _number(row.get("away_blocked_shots")),
            "inside_box_for": _number(row.get("away_shots_insidebox")),
            "offsides_for": _number(row.get("away_offsides")),
            "accurate_passes_for": _number(row.get("away_passes_accurate")),
            "pass_accuracy": _number(row.get("away_pass_accuracy")),
        },
    )
    return home, away


def _mean(
    samples: list[TeamMatchSample],
    metric: str,
    *,
    count: int,
    venue: str | None = None,
) -> float:
    eligible = samples if venue is None else [item for item in samples if item.venue == venue]
    values = [
        value
        for item in eligible[-count:]
        if (value := item.values.get(metric)) is not None
    ]
    if not values:
        return float("nan")
    return float(sum(values) / len(values))


def _team_features(
    samples: list[TeamMatchSample],
    *,
    venue: str,
) -> list[float]:
    values = [_mean(samples, metric, count=5) for metric in _BASE_METRICS]
    values.extend(_mean(samples, metric, count=10) for metric in _LONG_METRICS)
    values.extend(_mean(samples, metric, count=5, venue=venue) for metric in _VENUE_METRICS)
    return values


def _feature_vector(
    histories: dict[int, list[TeamMatchSample]],
    home_team_id: int,
    away_team_id: int,
) -> np.ndarray:
    home = histories.get(home_team_id, [])
    away = histories.get(away_team_id, [])
    return np.asarray(
        _team_features(home, venue="HOME") + _team_features(away, venue="AWAY"),
        dtype=float,
    )


def _safe_id(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _build_training(
    rows: tuple[dict[str, Any], ...],
) -> tuple[np.ndarray, np.ndarray, dict[int, list[TeamMatchSample]], int]:
    histories: dict[int, list[TeamMatchSample]] = {}
    features: list[np.ndarray] = []
    targets: list[float] = []
    usable_matches = 0

    for row in rows:
        home_id = _safe_id(row.get("home_team_id"))
        away_id = _safe_id(row.get("away_team_id"))
        home_corners = _number(row.get("home_corner_kicks"))
        away_corners = _number(row.get("away_corner_kicks"))
        if (
            home_id is None
            or away_id is None
            or home_id == away_id
            or home_corners is None
            or away_corners is None
        ):
            continue

        home_history = histories.setdefault(home_id, [])
        away_history = histories.setdefault(away_id, [])
        if (
            len(home_history) >= MIN_TEAM_HISTORY
            and len(away_history) >= MIN_TEAM_HISTORY
        ):
            features.append(_feature_vector(histories, home_id, away_id))
            targets.append(home_corners + away_corners)

        home_sample, away_sample = _team_samples(row)
        home_history.append(home_sample)
        away_history.append(away_sample)
        usable_matches += 1

    if features:
        x = np.vstack(features)
    else:
        x = np.empty((0, len(FEATURE_NAMES)), dtype=float)
    return x, np.asarray(targets, dtype=float), histories, usable_matches


def _fit_poisson(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float] | None:
    if len(y) < MIN_TRAINING_EXAMPLES:
        return None

    finite = np.isfinite(x)
    counts = finite.sum(axis=0)
    sums = np.where(finite, x, 0.0).sum(axis=0)
    means = np.divide(sums, counts, out=np.zeros(x.shape[1]), where=counts > 0)
    x_imputed = np.where(finite, x, means)
    scales = x_imputed.std(axis=0)
    scales = np.where(scales < 1e-6, 1.0, scales)
    z = (x_imputed - means) / scales
    design = np.column_stack([np.ones(len(z)), z])

    initial = np.zeros(design.shape[1], dtype=float)
    initial[0] = log(max(float(y.mean()), 0.5))

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        eta = np.clip(design @ beta, -6.0, 6.0)
        mu = np.exp(eta)
        penalty = 0.5 * RIDGE_PENALTY * float(np.dot(beta[1:], beta[1:]))
        value = float(np.sum(mu - y * eta) + penalty)
        residual = mu - y
        gradient = design.T @ residual
        gradient[1:] += RIDGE_PENALTY * beta[1:]
        return value, gradient

    result = minimize(
        fun=lambda beta: objective(beta)[0],
        x0=initial,
        jac=lambda beta: objective(beta)[1],
        method="L-BFGS-B",
        options={"maxiter": 500, "ftol": 1e-10},
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        return None
    return result.x, means, scales, float(result.fun)


def _json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return sha256(encoded).hexdigest()


def _payload_vector(vector: np.ndarray) -> dict[str, float | None]:
    return {
        name: (float(value) if isfinite(float(value)) else None)
        for name, value in zip(FEATURE_NAMES, vector, strict=True)
    }


class CornerPressureModelService:
    """Fit once per decision timestamp and estimate total corners per target fixture."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository
        self._cache_at: datetime | None = None
        self._artifact: CornerModelArtifact | None = None
        self._histories: dict[int, list[TeamMatchSample]] = {}
        self._fit_reason = "NOT_FITTED"
        self._fit_details: dict[str, Any] = {}

    def _prepare(self, decision_at: datetime) -> None:
        now = decision_at.astimezone(UTC)
        if self._cache_at == now:
            return

        rows = self._repository.corner_model_history(before=now, limit=HISTORY_LIMIT)
        x, y, histories, history_match_count = _build_training(rows)
        fitted = _fit_poisson(x, y)
        self._cache_at = now
        self._histories = histories

        if fitted is None:
            self._artifact = None
            self._fit_reason = "INSUFFICIENT_CORNER_MODEL_HISTORY"
            self._fit_details = {
                "history_match_count": history_match_count,
                "training_sample_size": int(len(y)),
                "minimum_training_examples": MIN_TRAINING_EXAMPLES,
            }
            return

        beta, means, scales, objective = fitted
        coefficients = {"intercept": float(beta[0])}
        coefficients.update(
            {
                name: float(value)
                for name, value in zip(FEATURE_NAMES, beta[1:], strict=True)
            }
        )
        feature_means = {
            name: float(value)
            for name, value in zip(FEATURE_NAMES, means, strict=True)
        }
        feature_scales = {
            name: float(value)
            for name, value in zip(FEATURE_NAMES, scales, strict=True)
        }
        identity = {
            "feature_version": FEATURE_VERSION,
            "training_cutoff": now.isoformat(),
            "training_sample_size": int(len(y)),
            "history_match_count": history_match_count,
            "ridge_penalty": RIDGE_PENALTY,
            "coefficients": coefficients,
            "feature_means": feature_means,
            "feature_scales": feature_scales,
        }
        model_version = MODEL_PREFIX + _json_hash(identity)
        artifact = CornerModelArtifact(
            model_version=model_version,
            trained_at=now,
            training_cutoff=now,
            feature_version=FEATURE_VERSION,
            training_sample_size=int(len(y)),
            history_match_count=history_match_count,
            ridge_penalty=RIDGE_PENALTY,
            coefficients=coefficients,
            feature_means=feature_means,
            feature_scales=feature_scales,
            training_payload={
                "objective": objective,
                "feature_names": FEATURE_NAMES,
                "minimum_team_history": MIN_TEAM_HISTORY,
                "minimum_training_examples": MIN_TRAINING_EXAMPLES,
                "history_limit": HISTORY_LIMIT,
                "structural_only": True,
                "bookmaker_features_used": False,
            },
        )
        self._repository.save_corner_model_version(artifact)
        self._artifact = artifact
        self._fit_reason = "MODEL_READY"
        self._fit_details = {
            "history_match_count": history_match_count,
            "training_sample_size": int(len(y)),
        }

    def estimate(
        self,
        fixture: dict[str, Any],
        *,
        decision_at: datetime,
    ) -> CornerEstimateResult:
        self._prepare(decision_at)
        if self._artifact is None:
            return CornerEstimateResult(None, self._fit_reason, dict(self._fit_details))

        home_id = _safe_id(fixture.get("home_team_id"))
        away_id = _safe_id(fixture.get("away_team_id"))
        if home_id is None or away_id is None or home_id == away_id:
            return CornerEstimateResult(
                None,
                "MISSING_CORNER_TEAM_IDENTITIES",
                {"home_team_id": home_id, "away_team_id": away_id},
            )

        home_history = self._histories.get(home_id, [])
        away_history = self._histories.get(away_id, [])
        if (
            len(home_history) < MIN_TEAM_HISTORY
            or len(away_history) < MIN_TEAM_HISTORY
        ):
            return CornerEstimateResult(
                None,
                "INSUFFICIENT_TEAM_CORNER_HISTORY",
                {
                    "home_history_size": len(home_history),
                    "away_history_size": len(away_history),
                    "minimum_team_history": MIN_TEAM_HISTORY,
                },
            )

        vector = _feature_vector(self._histories, home_id, away_id)
        means = np.asarray(
            [self._artifact.feature_means[name] for name in FEATURE_NAMES],
            dtype=float,
        )
        scales = np.asarray(
            [self._artifact.feature_scales[name] for name in FEATURE_NAMES],
            dtype=float,
        )
        imputed = np.where(np.isfinite(vector), vector, means)
        standardized = (imputed - means) / scales
        beta = np.asarray(
            [self._artifact.coefficients["intercept"]]
            + [self._artifact.coefficients[name] for name in FEATURE_NAMES],
            dtype=float,
        )
        eta = float(beta[0] + np.dot(standardized, beta[1:]))
        expected = exp(max(-6.0, min(6.0, eta)))
        if not isfinite(expected) or expected <= 0:
            return CornerEstimateResult(
                None,
                "INVALID_CORNER_MODEL_OUTPUT",
                {"eta": eta},
            )

        fixture_id = str(fixture["fixture_id"])
        snapshot = CornerFeatureSnapshot(
            fixture_id=fixture_id,
            decision_at=decision_at.astimezone(UTC),
            model_version=self._artifact.model_version,
            expected_total_corners=expected,
            home_history_size=len(home_history),
            away_history_size=len(away_history),
            feature_payload={
                "feature_version": FEATURE_VERSION,
                "raw_features": _payload_vector(vector),
                "imputed_features": {
                    name: float(value)
                    for name, value in zip(FEATURE_NAMES, imputed, strict=True)
                },
                "home_history_size": len(home_history),
                "away_history_size": len(away_history),
            },
        )
        self._repository.save_corner_feature_snapshot(snapshot)
        return CornerEstimateResult(
            CornerEstimate(
                expected_total_corners=expected,
                model=self._artifact,
                snapshot=snapshot,
            ),
            "MODEL_READY",
            {
                "training_sample_size": self._artifact.training_sample_size,
                "history_match_count": self._artifact.history_match_count,
            },
        )
