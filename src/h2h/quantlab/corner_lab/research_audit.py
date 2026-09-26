"""Chronological research-only validation for CornerLab V2 Poisson model."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from math import exp, lgamma, log, sqrt
from statistics import fmean, variance
from typing import Any

import numpy as np
from scipy.stats import poisson

from h2h.quantlab.corner_lab.model import (
    FEATURE_NAMES,
    HISTORY_LIMIT,
    MIN_TEAM_HISTORY,
    MIN_TRAINING_EXAMPLES,
    _build_training,
    _feature_vector,
    _fit_poisson,
    _number,
    _safe_id,
    _team_samples,
)


HOLDOUT_FRACTIONS = (0.40, 0.35, 0.30, 0.25, 0.20, 0.15)
STANDARD_HALF_LINES = tuple(value + 0.5 for value in range(4, 15))
_EPSILON = 1e-12


def _rounded(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _score_binary(probability: float, outcome: float) -> tuple[float, float]:
    p = min(1.0 - _EPSILON, max(_EPSILON, probability))
    brier = (p - outcome) ** 2
    log_loss = -(outcome * log(p) + (1.0 - outcome) * log(1.0 - p))
    return brier, log_loss


def _pick_split(
    rows: tuple[dict[str, Any], ...],
) -> tuple[
    int,
    np.ndarray,
    np.ndarray,
    dict[int, list[Any]],
    int,
] | None:
    """Choose the earliest split with >=80 train examples and a useful future holdout."""
    n_rows = len(rows)
    if n_rows < MIN_TRAINING_EXAMPLES + 20:
        return None

    for holdout_fraction in HOLDOUT_FRACTIONS:
        cutoff = int(n_rows * (1.0 - holdout_fraction))
        if cutoff <= 0 or n_rows - cutoff < 30:
            continue
        x, y, histories, usable = _build_training(rows[:cutoff])
        if len(y) >= MIN_TRAINING_EXAMPLES:
            return cutoff, x, y, histories, usable
    return None


def _predict_mu(
    vector: np.ndarray,
    *,
    beta: np.ndarray,
    means: np.ndarray,
    scales: np.ndarray,
) -> float:
    finite = np.isfinite(vector)
    imputed = np.where(finite, vector, means)
    z = (imputed - means) / scales
    design = np.concatenate(([1.0], z))
    eta = float(np.clip(design @ beta, -6.0, 6.0))
    return float(exp(eta))


def _summarize_prediction_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}

    actuals = [float(item["actual"]) for item in rows]
    predictions = [float(item["mu"]) for item in rows]
    residuals = [actual - predicted for actual, predicted in zip(actuals, predictions)]
    observed_mean = fmean(actuals)
    predicted_mean = fmean(predictions)
    observed_variance = variance(actuals) if len(actuals) > 1 else 0.0
    residual_variance = variance(residuals) if len(residuals) > 1 else 0.0
    poisson_ll = sum(
        actual * log(mu) - mu - lgamma(actual + 1.0)
        for actual, mu in zip(actuals, predictions)
        if mu > 0
    )
    pearson_terms = [
        ((actual - mu) ** 2) / mu
        for actual, mu in zip(actuals, predictions)
        if mu > 0
    ]
    pearson_dispersion = fmean(pearson_terms) if pearson_terms else None
    variance_to_mean = (
        observed_variance / observed_mean if observed_mean > 0 else None
    )

    return {
        "n": len(rows),
        "observed_mean": _rounded(observed_mean),
        "predicted_mean": _rounded(predicted_mean),
        "mae": _rounded(fmean(abs(item) for item in residuals)),
        "rmse": _rounded(sqrt(fmean(item * item for item in residuals))),
        "observed_variance": _rounded(observed_variance),
        "residual_variance": _rounded(residual_variance),
        "variance_to_mean": _rounded(variance_to_mean),
        "pearson_dispersion": _rounded(pearson_dispersion),
        "poisson_log_likelihood": _rounded(poisson_ll),
        "mean_poisson_log_likelihood": _rounded(poisson_ll / len(rows)),
        "overdispersion_signal": bool(
            (variance_to_mean is not None and variance_to_mean > 1.25)
            or (pearson_dispersion is not None and pearson_dispersion > 1.25)
        ),
    }


def _line_calibration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line in STANDARD_HALF_LINES:
        briers: list[float] = []
        log_losses: list[float] = []
        probabilities: list[float] = []
        outcomes: list[float] = []
        threshold = int(line)
        for item in rows:
            mu = float(item["mu"])
            actual = float(item["actual"])
            probability_over = 1.0 - float(poisson.cdf(threshold, mu))
            outcome_over = 1.0 if actual > line else 0.0
            brier, loss = _score_binary(probability_over, outcome_over)
            briers.append(brier)
            log_losses.append(loss)
            probabilities.append(probability_over)
            outcomes.append(outcome_over)
        if not probabilities:
            continue
        result.append(
            {
                "line": line,
                "n": len(probabilities),
                "mean_predicted_over": _rounded(fmean(probabilities)),
                "observed_over_rate": _rounded(fmean(outcomes)),
                "calibration_gap": _rounded(
                    fmean(probabilities) - fmean(outcomes)
                ),
                "brier": _rounded(fmean(briers)),
                "log_loss": _rounded(fmean(log_losses)),
            }
        )
    return result


def run_cornerlab_historical_holdout(
    rows: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Fit on earlier rows and evaluate only chronologically later matches."""
    split = _pick_split(rows)
    if split is None:
        return {
            "status": "INSUFFICIENT_HOLDOUT_TRAINING_SAMPLE",
            "history_rows": len(rows),
            "minimum_training_examples": MIN_TRAINING_EXAMPLES,
        }

    cutoff, x_train, y_train, histories, train_usable = split
    fitted = _fit_poisson(x_train, y_train)
    if fitted is None:
        return {
            "status": "POISSON_FIT_FAILED",
            "history_rows": len(rows),
            "split_index": cutoff,
            "train_training_examples": len(y_train),
        }

    beta, means, scales, objective = fitted
    predictions: list[dict[str, Any]] = []
    holdout_usable_matches = 0

    for row in rows[cutoff:]:
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
            vector = _feature_vector(histories, home_id, away_id)
            mu = _predict_mu(vector, beta=beta, means=means, scales=scales)
            predictions.append(
                {
                    "fixture_id": str(row.get("fixture_id") or ""),
                    "kickoff_at": row.get("kickoff_at"),
                    "league": str(row.get("competition_name") or "UNKNOWN"),
                    "actual": float(home_corners + away_corners),
                    "mu": mu,
                }
            )

        home_sample, away_sample = _team_samples(row)
        home_history.append(home_sample)
        away_history.append(away_sample)
        holdout_usable_matches += 1

    by_league: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in predictions:
        by_league[str(item["league"])].append(item)
    league_split = [
        {"league": league, **_summarize_prediction_rows(items)}
        for league, items in by_league.items()
        if len(items) >= 8
    ]
    league_split.sort(key=lambda item: (-int(item["n"]), str(item["league"])))

    return {
        "status": "OK",
        "method": "chronological_single_holdout_expanding_history",
        "structural_only": True,
        "bookmaker_features_used": False,
        "history_rows": len(rows),
        "split_index": cutoff,
        "train_history_matches": train_usable,
        "train_training_examples": len(y_train),
        "holdout_history_matches": holdout_usable_matches,
        "holdout_predictions": len(predictions),
        "holdout_fraction": _rounded((len(rows) - cutoff) / len(rows)),
        "feature_count": len(FEATURE_NAMES),
        "fit_objective": _rounded(float(objective)),
        "summary": _summarize_prediction_rows(predictions),
        "line_calibration_over": _line_calibration(predictions),
        "league_split_n_ge_8": league_split[:30],
        "bookmaker_split": {
            "status": "NOT_AVAILABLE",
            "reason": (
                "Historical training fixtures do not have a complete aligned pre-match "
                "bookmaker quote history; bookmaker calibration must wait for settled "
                "target snapshots/quotes."
            ),
        },
        "interpretation_rule": {
            "negative_binomial_candidate_if": (
                "variance_to_mean > 1.25 or pearson_dispersion > 1.25"
            ),
            "threshold_is_research_heuristic": True,
        },
    }


def collect_cornerlab_historical_holdout(repository: Any) -> dict[str, Any]:
    rows = repository.corner_model_history(
        before=datetime.now(UTC),
        limit=HISTORY_LIMIT,
    )
    return run_cornerlab_historical_holdout(rows)


def log_cornerlab_historical_holdout(repository: Any, logger: logging.Logger) -> None:
    report = collect_cornerlab_historical_holdout(repository)
    logger.info(
        "QuantLab CornerLab V2 historical holdout payload=%s",
        json.dumps(report, sort_keys=True, default=str, separators=(",", ":")),
    )
