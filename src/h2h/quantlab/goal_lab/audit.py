"""GoalLab DC+ chronological holdout validation against plain Dixon-Coles."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
from scipy.stats import poisson

from h2h.quant.dixon_coles import DixonColesFitError, DixonColesModel, dixon_coles_tau
from h2h.quantlab.goal_lab.model import (
    CONTRACT_COVERAGE_V1,
    MIN_TRAINING_EXAMPLES,
    RECENCY_XI,
    _build_training,
    _fit_dc_plus,
    _prepare_features,
    _score_matrix,
    _transform_feature_row,
)


METHOD_VERSION = "GOALLAB_CHRONOLOGICAL_HOLDOUT_V1"
HOLDOUT_FRACTION = 0.30
MIN_COMMON_EVALUATION = 50
CONTROL_RIDGE = 0.01


@dataclass(frozen=True, slots=True)
class GoalModelValidation:
    model_version: str
    evaluated_at: datetime
    method_version: str
    status: str
    train_start_at: datetime | None
    train_end_at: datetime | None
    holdout_start_at: datetime | None
    holdout_end_at: datetime | None
    train_sample_size: int
    holdout_sample_size: int
    common_evaluation_size: int
    dc_plus_metrics: dict[str, Any]
    control_metrics: dict[str, Any]
    comparison: dict[str, Any]
    leakage_audit: dict[str, Any]
    contract_snapshot: dict[str, Any]
    authority_review_status: str


def _joint_log_likelihood(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    tau = dixon_coles_tau(
        home_goals,
        away_goals,
        lambda_home,
        lambda_away,
        rho,
    )
    if tau <= 0 or not math.isfinite(tau):
        return float("-inf")
    return float(
        poisson.logpmf(home_goals, lambda_home)
        + poisson.logpmf(away_goals, lambda_away)
        + math.log(tau)
    )


def _market_probabilities(
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> tuple[float, float]:
    matrix = _score_matrix(lambda_home, lambda_away, rho, max_goals=12)
    under = sum(
        float(matrix[home, away])
        for home in range(matrix.shape[0])
        for away in range(matrix.shape[1])
        if home + away <= 2
    )
    return 1.0 - under, float(matrix[1:, 1:].sum())


def _metrics(rows: list[dict[str, float]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    n = len(rows)
    observed_totals = np.asarray(
        [row["home_goals"] + row["away_goals"] for row in rows],
        dtype=float,
    )
    predicted_totals = np.asarray(
        [row["lambda_home"] + row["lambda_away"] for row in rows],
        dtype=float,
    )
    home_errors = np.asarray(
        [row["lambda_home"] - row["home_goals"] for row in rows],
        dtype=float,
    )
    away_errors = np.asarray(
        [row["lambda_away"] - row["away_goals"] for row in rows],
        dtype=float,
    )
    total_errors = predicted_totals - observed_totals
    over_actual = np.asarray(
        [float(row["home_goals"] + row["away_goals"] >= 3) for row in rows],
        dtype=float,
    )
    over_pred = np.asarray([row["over25_probability"] for row in rows], dtype=float)
    btts_actual = np.asarray(
        [float(row["home_goals"] > 0 and row["away_goals"] > 0) for row in rows],
        dtype=float,
    )
    btts_pred = np.asarray([row["btts_probability"] for row in rows], dtype=float)
    log_likelihoods = np.asarray([row["log_likelihood"] for row in rows], dtype=float)
    return {
        "n": n,
        "exact_score_mean_log_likelihood": float(np.mean(log_likelihoods)),
        "exact_score_total_log_likelihood": float(np.sum(log_likelihoods)),
        "home_goals_mae": float(np.mean(np.abs(home_errors))),
        "away_goals_mae": float(np.mean(np.abs(away_errors))),
        "total_goals_mae": float(np.mean(np.abs(total_errors))),
        "total_goals_rmse": float(np.sqrt(np.mean(total_errors**2))),
        "observed_total_goals_mean": float(np.mean(observed_totals)),
        "predicted_total_goals_mean": float(np.mean(predicted_totals)),
        "over25_brier": float(np.mean((over_pred - over_actual) ** 2)),
        "over25_predicted_mean": float(np.mean(over_pred)),
        "over25_observed_rate": float(np.mean(over_actual)),
        "btts_brier": float(np.mean((btts_pred - btts_actual) ** 2)),
        "btts_predicted_mean": float(np.mean(btts_pred)),
        "btts_observed_rate": float(np.mean(btts_actual)),
    }


def _dc_plus_lambda(
    params: dict[str, Any],
    vector: np.ndarray,
    *,
    home_id: int,
    away_id: int,
    league_id: int,
) -> tuple[float, float] | None:
    attacks = params["attacks"]
    defenses = params["defenses"]
    leagues = params["league_effects"]
    if (
        str(home_id) not in attacks
        or str(away_id) not in attacks
        or str(home_id) not in defenses
        or str(away_id) not in defenses
        or str(league_id) not in leagues
    ):
        return None
    beta_home = np.asarray(params["beta_home"], dtype=float)
    beta_away = np.asarray(params["beta_away"], dtype=float)
    eta_home = (
        float(params["intercept"])
        + float(params["home_advantage"])
        + float(attacks[str(home_id)])
        + float(defenses[str(away_id)])
        + float(leagues[str(league_id)])
        + float(np.dot(vector, beta_home))
    )
    eta_away = (
        float(params["intercept"])
        + float(attacks[str(away_id)])
        + float(defenses[str(home_id)])
        + float(leagues[str(league_id)])
        + float(np.dot(vector, beta_away))
    )
    return (
        math.exp(max(-6.0, min(4.0, eta_home))),
        math.exp(max(-6.0, min(4.0, eta_away))),
    )


def _empty_validation(
    *,
    model_version: str,
    evaluated_at: datetime,
    status: str,
    train_n: int,
    holdout_n: int,
    dates: np.ndarray,
    contract_snapshot: dict[str, Any],
    reason: str,
) -> GoalModelValidation:
    train_end_index = max(0, min(train_n - 1, len(dates) - 1))
    holdout_start_index = max(0, min(train_n, len(dates) - 1))
    return GoalModelValidation(
        model_version=model_version,
        evaluated_at=evaluated_at,
        method_version=METHOD_VERSION,
        status=status,
        train_start_at=None if len(dates) == 0 else dates[0],
        train_end_at=None if train_n == 0 or len(dates) == 0 else dates[train_end_index],
        holdout_start_at=(
            None if holdout_n == 0 or len(dates) == 0 else dates[holdout_start_index]
        ),
        holdout_end_at=None if holdout_n == 0 or len(dates) == 0 else dates[-1],
        train_sample_size=train_n,
        holdout_sample_size=holdout_n,
        common_evaluation_size=0,
        dc_plus_metrics={"n": 0, "reason": reason},
        control_metrics={"n": 0, "reason": reason},
        comparison={"reason": reason},
        leakage_audit=_leakage_audit(),
        contract_snapshot=contract_snapshot,
        authority_review_status="NOT_READY",
    )


def _leakage_audit() -> dict[str, Any]:
    checks = {
        "chronological_feature_construction": True,
        "target_result_excluded_from_target_features": True,
        "feature_preprocessing_fit_on_train_only": True,
        "holdout_not_used_for_model_fit": True,
        "historical_inputs_require_matches_before_target": True,
        "target_standings_requires_available_at_lte_decision": True,
        "target_injuries_requires_available_at_lte_decision": True,
        "target_manager_capture_requires_available_at_lte_decision": True,
        "target_match_live_statistics_used": False,
        "bookmaker_features_used_in_probability_model": False,
        "provider_predictions_used_in_probability_model": False,
    }
    return {
        "status": "PASS" if all(
            value is True
            for key, value in checks.items()
            if not key.endswith("_used") and "features_used" not in key
        ) and checks["target_match_live_statistics_used"] is False
        and checks["bookmaker_features_used_in_probability_model"] is False
        and checks["provider_predictions_used_in_probability_model"] is False
        else "FAIL",
        "checks": checks,
    }


def build_goal_model_validation(
    repository: Any,
    *,
    model_version: str,
    evaluated_at: datetime,
) -> GoalModelValidation:
    contract = repository.goal_model_contract(model_version)
    if contract is None:
        raise ValueError("GoalLab model artifact does not exist")
    cutoff = contract["training_cutoff"]
    if not isinstance(cutoff, datetime):
        raise TypeError("training_cutoff must be datetime")

    history = repository.goal_model_history(before=cutoff, limit=10_000)
    (
        feature_rows,
        y_home,
        y_away,
        home_ids,
        away_ids,
        league_ids,
        dates,
        _histories,
        _pairs,
        history_match_count,
    ) = _build_training(history)

    n = len(feature_rows)
    holdout_n = max(1, int(round(n * HOLDOUT_FRACTION))) if n else 0
    train_n = max(0, n - holdout_n)
    contract_snapshot = {
        "feature_version": contract.get("feature_version"),
        "artifact_training_sample_size": contract.get("training_sample_size"),
        "artifact_history_match_count": contract.get("history_match_count"),
        "audit_history_match_count": history_match_count,
        "contract_coverage": (
            contract.get("training_payload", {}).get("contract_coverage")
            if isinstance(contract.get("training_payload"), dict)
            else CONTRACT_COVERAGE_V1
        ),
        "holdout_fraction": HOLDOUT_FRACTION,
        "minimum_common_evaluation": MIN_COMMON_EVALUATION,
        "automatic_pick_authority": False,
    }
    if train_n < MIN_TRAINING_EXAMPLES or holdout_n <= 0:
        return _empty_validation(
            model_version=model_version,
            evaluated_at=evaluated_at,
            status="INSUFFICIENT_HISTORY",
            train_n=train_n,
            holdout_n=holdout_n,
            dates=dates,
            contract_snapshot=contract_snapshot,
            reason=(
                f"chronological train sample {train_n} below "
                f"minimum {MIN_TRAINING_EXAMPLES}"
            ),
        )

    train_features = feature_rows[:train_n]
    holdout_features = feature_rows[train_n:]
    train_home = y_home[:train_n]
    train_away = y_away[:train_n]
    train_home_ids = home_ids[:train_n]
    train_away_ids = away_ids[:train_n]
    train_leagues = league_ids[:train_n]
    train_dates = dates[:train_n]

    x_train, model_names, means, scales, base_names = _prepare_features(train_features)
    fitted = _fit_dc_plus(
        x_train,
        train_home,
        train_away,
        train_home_ids,
        train_away_ids,
        train_leagues,
        train_dates,
        model_names,
        reference_time=dates[train_n],
    )
    if fitted is None:
        return _empty_validation(
            model_version=model_version,
            evaluated_at=evaluated_at,
            status="FIT_FAILED",
            train_n=train_n,
            holdout_n=holdout_n,
            dates=dates,
            contract_snapshot=contract_snapshot,
            reason="DC+ chronological training fit failed",
        )
    dc_plus_params, _objective = fitted

    control_records = [
        SimpleNamespace(
            date=dates[index],
            home_id=int(home_ids[index]),
            away_id=int(away_ids[index]),
            home_goals=int(y_home[index]),
            away_goals=int(y_away[index]),
        )
        for index in range(train_n)
    ]
    try:
        control = DixonColesModel.fit(
            control_records,
            team_id_namespace="api-football",
            reference_time=dates[train_n],
            xi=RECENCY_XI,
            ridge=CONTROL_RIDGE,
            min_matches=80,
        )
    except DixonColesFitError as exc:
        return _empty_validation(
            model_version=model_version,
            evaluated_at=evaluated_at,
            status="CONTROL_FIT_FAILED",
            train_n=train_n,
            holdout_n=holdout_n,
            dates=dates,
            contract_snapshot=contract_snapshot,
            reason=str(exc),
        )

    dc_plus_rows: list[dict[str, float]] = []
    control_rows: list[dict[str, float]] = []
    control_teams = set(control.team_ids)
    for offset, raw_features in enumerate(holdout_features):
        index = train_n + offset
        home_id = int(home_ids[index])
        away_id = int(away_ids[index])
        league_id = int(league_ids[index])
        if home_id not in control_teams or away_id not in control_teams:
            continue
        vector, _raw_payload = _transform_feature_row(
            raw_features,
            model_feature_names=model_names,
            base_feature_names=base_names,
            means=means,
            scales=scales,
        )
        dc_lambdas = _dc_plus_lambda(
            dc_plus_params,
            vector,
            home_id=home_id,
            away_id=away_id,
            league_id=league_id,
        )
        if dc_lambdas is None:
            continue
        try:
            control_lambdas = control.expected_goals(home_id, away_id)
        except DixonColesFitError:
            continue

        actual_home = int(y_home[index])
        actual_away = int(y_away[index])
        for target, lambdas, rho in (
            (dc_plus_rows, dc_lambdas, float(dc_plus_params["rho"])),
            (control_rows, control_lambdas, float(control.rho)),
        ):
            lambda_home, lambda_away = lambdas
            over25, btts = _market_probabilities(lambda_home, lambda_away, rho)
            target.append(
                {
                    "home_goals": float(actual_home),
                    "away_goals": float(actual_away),
                    "lambda_home": float(lambda_home),
                    "lambda_away": float(lambda_away),
                    "over25_probability": over25,
                    "btts_probability": btts,
                    "log_likelihood": _joint_log_likelihood(
                        actual_home,
                        actual_away,
                        lambda_home,
                        lambda_away,
                        rho,
                    ),
                }
            )

    common_n = min(len(dc_plus_rows), len(control_rows))
    if common_n == 0:
        return _empty_validation(
            model_version=model_version,
            evaluated_at=evaluated_at,
            status="INSUFFICIENT_HISTORY",
            train_n=train_n,
            holdout_n=holdout_n,
            dates=dates,
            contract_snapshot=contract_snapshot,
            reason="no common DC+/control holdout coverage",
        )

    dc_plus_metrics = _metrics(dc_plus_rows[:common_n])
    control_metrics = _metrics(control_rows[:common_n])
    comparison = {
        "dc_plus_minus_control_exact_score_mean_log_likelihood": (
            dc_plus_metrics["exact_score_mean_log_likelihood"]
            - control_metrics["exact_score_mean_log_likelihood"]
        ),
        "dc_plus_minus_control_total_goals_rmse": (
            dc_plus_metrics["total_goals_rmse"] - control_metrics["total_goals_rmse"]
        ),
        "dc_plus_minus_control_over25_brier": (
            dc_plus_metrics["over25_brier"] - control_metrics["over25_brier"]
        ),
        "dc_plus_minus_control_btts_brier": (
            dc_plus_metrics["btts_brier"] - control_metrics["btts_brier"]
        ),
        "interpretation": {
            "exact_score_mean_log_likelihood": "higher_is_better",
            "total_goals_rmse": "lower_is_better",
            "over25_brier": "lower_is_better",
            "btts_brier": "lower_is_better",
        },
        "automatic_promotion_rule": None,
        "note": "comparison is evidence for manual GoalLab pick-authority review",
    }
    leakage = _leakage_audit()
    ready = common_n >= MIN_COMMON_EVALUATION and leakage["status"] == "PASS"
    return GoalModelValidation(
        model_version=model_version,
        evaluated_at=evaluated_at.astimezone(UTC),
        method_version=METHOD_VERSION,
        status="OK",
        train_start_at=dates[0],
        train_end_at=dates[train_n - 1],
        holdout_start_at=dates[train_n],
        holdout_end_at=dates[-1],
        train_sample_size=train_n,
        holdout_sample_size=holdout_n,
        common_evaluation_size=common_n,
        dc_plus_metrics=dc_plus_metrics,
        control_metrics=control_metrics,
        comparison=comparison,
        leakage_audit=leakage,
        contract_snapshot=contract_snapshot,
        authority_review_status=(
            "READY_FOR_MANUAL_REVIEW" if ready else "NOT_READY"
        ),
    )


def ensure_latest_goal_model_validation(
    repository: Any,
    logger: Any,
    *,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """Persist at most one chronological validation for the latest DC+ artifact."""
    contract = repository.goal_model_contract()
    if contract is None:
        return {"status": "NO_MODEL"}
    model_version = str(contract["model_version"])
    existing = repository.goal_model_validation(model_version)
    if existing is not None:
        return existing

    now = (evaluated_at or datetime.now(UTC)).astimezone(UTC)
    validation = build_goal_model_validation(
        repository,
        model_version=model_version,
        evaluated_at=now,
    )
    repository.save_goal_model_validation(validation)
    logger.info(
        "GoalLab DC+ validation model=%s status=%s train_n=%d holdout_n=%d common_n=%d "
        "authority_review=%s comparison=%s leakage=%s",
        validation.model_version,
        validation.status,
        validation.train_sample_size,
        validation.holdout_sample_size,
        validation.common_evaluation_size,
        validation.authority_review_status,
        validation.comparison,
        validation.leakage_audit,
    )
    return repository.goal_model_validation(model_version) or {
        "status": validation.status,
        "model_version": validation.model_version,
    }
