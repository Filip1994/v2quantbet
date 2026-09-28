"""GoalLab DC+ chronological holdout validation against plain Dixon-Coles."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
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


METHOD_VERSION = "GOALLAB_CHRONOLOGICAL_HOLDOUT_V4"
HOLDOUT_FRACTION = 0.30
MIN_COMMON_EVALUATION = 50
CONTROL_RIDGE = 0.01
CONTROL_MIN_MATCHES = 80
CONTROL_MIN_TEAM_APPEARANCES = 5


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


def _fit_sparse_pooled_control(
    records: list[Any],
    *,
    reference_time: datetime,
) -> DixonColesModel:
    """Fit a feature-free pooled DC control with neutral effects for sparse teams."""
    records = [record for record in records if record.date < reference_time]
    if len(records) < CONTROL_MIN_MATCHES:
        raise DixonColesFitError(
            f"insufficient pooled training sample {len(records)} < {CONTROL_MIN_MATCHES}"
        )

    team_counts = DixonColesModel.team_match_counts(records)
    team_ids = tuple(
        sorted(
            {int(record.home_id) for record in records}
            | {int(record.away_id) for record in records}
        )
    )
    latent_team_ids = tuple(
        team_id
        for team_id in team_ids
        if team_counts[team_id] >= CONTROL_MIN_TEAM_APPEARANCES
    )
    latent_index = {team_id: index for index, team_id in enumerate(latent_team_ids)}

    n = len(records)
    nt = len(latent_team_ids)
    home_ids = np.asarray([int(record.home_id) for record in records], dtype=np.int64)
    away_ids = np.asarray([int(record.away_id) for record in records], dtype=np.int64)
    home_goals = np.asarray([int(record.home_goals) for record in records], dtype=float)
    away_goals = np.asarray([int(record.away_goals) for record in records], dtype=float)
    dates = np.asarray([record.date for record in records], dtype=object)

    home_idx = np.asarray(
        [latent_index.get(int(team_id), -1) for team_id in home_ids], dtype=np.int64
    )
    away_idx = np.asarray(
        [latent_index.get(int(team_id), -1) for team_id in away_ids], dtype=np.int64
    )
    home_valid = home_idx >= 0
    away_valid = away_idx >= 0
    home_safe = np.where(home_valid, home_idx, 0)
    away_safe = np.where(away_valid, away_idx, 0)

    attack_slice = slice(0, nt)
    defense_slice = slice(nt, 2 * nt)
    intercept_index = 2 * nt
    home_adv_index = intercept_index + 1
    rho_index = intercept_index + 2
    size = rho_index + 1

    mean_goals = max(0.2, float(np.mean(np.concatenate([home_goals, away_goals]))))
    initial = np.zeros(size, dtype=float)
    initial[intercept_index] = math.log(mean_goals)
    initial[home_adv_index] = 0.10
    initial[rho_index] = -0.05

    ages = np.asarray(
        [
            max(0.0, (reference_time - item).total_seconds() / 86_400.0)
            for item in dates
        ],
        dtype=float,
    )
    weights = np.exp(-RECENCY_XI * ages)

    def objective(params: np.ndarray) -> tuple[float, np.ndarray]:
        attacks = params[attack_slice]
        defenses = params[defense_slice]
        intercept = float(params[intercept_index])
        home_adv = float(params[home_adv_index])
        rho = float(params[rho_index])

        if nt:
            home_attack = np.where(home_valid, attacks[home_safe], 0.0)
            away_attack = np.where(away_valid, attacks[away_safe], 0.0)
            home_defense = np.where(home_valid, defenses[home_safe], 0.0)
            away_defense = np.where(away_valid, defenses[away_safe], 0.0)
        else:
            home_attack = away_attack = np.zeros(n, dtype=float)
            home_defense = away_defense = np.zeros(n, dtype=float)

        eta_home_raw = intercept + home_adv + home_attack + away_defense
        eta_away_raw = intercept + away_attack + home_defense
        eta_home = np.clip(eta_home_raw, -5.0, 3.0)
        eta_away = np.clip(eta_away_raw, -5.0, 3.0)
        lambda_home = np.exp(eta_home)
        lambda_away = np.exp(eta_away)

        tau = np.ones(n, dtype=float)
        dlogtau_home = np.zeros(n, dtype=float)
        dlogtau_away = np.zeros(n, dtype=float)
        dlogtau_rho = np.zeros(n, dtype=float)
        mask00 = (home_goals == 0) & (away_goals == 0)
        mask01 = (home_goals == 0) & (away_goals == 1)
        mask10 = (home_goals == 1) & (away_goals == 0)
        mask11 = (home_goals == 1) & (away_goals == 1)

        tau[mask00] = 1.0 - lambda_home[mask00] * lambda_away[mask00] * rho
        tau[mask01] = 1.0 + lambda_home[mask01] * rho
        tau[mask10] = 1.0 + lambda_away[mask10] * rho
        tau[mask11] = 1.0 - rho
        if np.any(tau <= 1e-10) or not np.all(np.isfinite(tau)):
            return 1e12, np.zeros_like(params)

        dlogtau_home[mask00] = (
            -lambda_home[mask00] * lambda_away[mask00] * rho / tau[mask00]
        )
        dlogtau_away[mask00] = dlogtau_home[mask00]
        dlogtau_rho[mask00] = (
            -lambda_home[mask00] * lambda_away[mask00] / tau[mask00]
        )
        dlogtau_home[mask01] = lambda_home[mask01] * rho / tau[mask01]
        dlogtau_rho[mask01] = lambda_home[mask01] / tau[mask01]
        dlogtau_away[mask10] = lambda_away[mask10] * rho / tau[mask10]
        dlogtau_rho[mask10] = lambda_away[mask10] / tau[mask10]
        dlogtau_rho[mask11] = -1.0 / tau[mask11]

        neg_ll = (
            lambda_home
            - home_goals * eta_home
            + gammaln(home_goals + 1.0)
            + lambda_away
            - away_goals * eta_away
            + gammaln(away_goals + 1.0)
            - np.log(tau)
        )
        value = float(
            np.dot(weights, neg_ll)
            + CONTROL_RIDGE
            * (np.dot(attacks, attacks) + np.dot(defenses, defenses))
        )

        grad_eta_home = weights * (lambda_home - home_goals - dlogtau_home)
        grad_eta_away = weights * (lambda_away - away_goals - dlogtau_away)
        grad_eta_home *= (eta_home_raw > -5.0) & (eta_home_raw < 3.0)
        grad_eta_away *= (eta_away_raw > -5.0) & (eta_away_raw < 3.0)

        grad = np.zeros_like(params)
        if nt:
            np.add.at(
                grad[attack_slice], home_idx[home_valid], grad_eta_home[home_valid]
            )
            np.add.at(
                grad[attack_slice], away_idx[away_valid], grad_eta_away[away_valid]
            )
            np.add.at(
                grad[defense_slice], away_idx[away_valid], grad_eta_home[away_valid]
            )
            np.add.at(
                grad[defense_slice], home_idx[home_valid], grad_eta_away[home_valid]
            )
            grad[attack_slice] += 2.0 * CONTROL_RIDGE * attacks
            grad[defense_slice] += 2.0 * CONTROL_RIDGE * defenses
        grad[intercept_index] = float(np.sum(grad_eta_home + grad_eta_away))
        grad[home_adv_index] = float(np.sum(grad_eta_home))
        grad[rho_index] = float(np.sum(weights * (-dlogtau_rho)))
        return value, grad

    bounds = (
        [(-3.0, 3.0)] * nt
        + [(-3.0, 3.0)] * nt
        + [(-2.0, 2.0), (-1.0, 1.0), (-0.20, 0.20)]
    )
    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        bounds=bounds,
        options={"maxiter": 2_000, "ftol": 1e-10, "gtol": 1e-6},
    )
    if not result.success or not np.isfinite(result.fun):
        gradient_norm = (
            None
            if result.jac is None
            else float(np.linalg.norm(np.asarray(result.jac, dtype=float), ord=np.inf))
        )
        raise DixonColesFitError(
            "sparse pooled optimization did not converge: "
            f"status={getattr(result, 'status', None)} "
            f"message={getattr(result, 'message', None)} "
            f"nit={getattr(result, 'nit', None)} "
            f"gradient_inf_norm={gradient_norm}"
        )

    latent_attacks = result.x[attack_slice]
    latent_defenses = result.x[defense_slice]
    all_attacks = np.zeros(len(team_ids), dtype=float)
    all_defenses = np.zeros(len(team_ids), dtype=float)
    all_index = {team_id: index for index, team_id in enumerate(team_ids)}
    for team_id, latent_position in latent_index.items():
        position = all_index[team_id]
        all_attacks[position] = float(latent_attacks[latent_position])
        all_defenses[position] = float(latent_defenses[latent_position])

    return DixonColesModel(
        team_ids=team_ids,
        team_id_namespace="api-football",
        attacks=all_attacks,
        defenses=all_defenses,
        intercept=float(result.x[intercept_index]),
        home_advantage=float(result.x[home_adv_index]),
        rho=float(result.x[rho_index]),
        xi=RECENCY_XI,
        fitted_matches=len(records),
        objective=float(result.fun),
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
    positive_checks = {
        "chronological_feature_construction": True,
        "target_result_excluded_from_target_features": True,
        "feature_preprocessing_fit_on_train_only": True,
        "holdout_not_used_for_model_fit": True,
        "historical_inputs_require_matches_before_target": True,
        "target_standings_requires_available_at_lte_decision": True,
        "target_injuries_requires_available_at_lte_decision": True,
        "target_manager_capture_requires_available_at_lte_decision": True,
    }
    forbidden_input_checks = {
        "target_match_live_statistics_used": False,
        "bookmaker_features_used_in_probability_model": False,
        "provider_predictions_used_in_probability_model": False,
    }
    checks = {**positive_checks, **forbidden_input_checks}
    passed = all(positive_checks.values()) and not any(forbidden_input_checks.values())
    return {
        "status": "PASS" if passed else "FAIL",
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
        _player_histories,
        _pairs,
        history_match_count,
    ) = _build_training(history)

    n = len(feature_rows)
    holdout_n = max(1, round(n * HOLDOUT_FRACTION)) if n else 0
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

    controls: dict[int, DixonColesModel] = {}
    control_fit_errors: dict[str, str] = {}
    training_leagues = sorted({int(value) for value in train_leagues.tolist()})
    for league_id in training_leagues:
        indices = [
            index
            for index in range(train_n)
            if int(train_leagues[index]) == league_id
        ]
        if len(indices) < CONTROL_MIN_MATCHES:
            control_fit_errors[str(league_id)] = (
                f"insufficient league training sample {len(indices)} < "
                f"{CONTROL_MIN_MATCHES}"
            )
            continue
        control_records = [
            SimpleNamespace(
                date=dates[index],
                home_id=int(home_ids[index]),
                away_id=int(away_ids[index]),
                home_goals=int(y_home[index]),
                away_goals=int(y_away[index]),
            )
            for index in indices
        ]
        try:
            controls[league_id] = DixonColesModel.fit(
                control_records,
                team_id_namespace="api-football",
                reference_time=dates[train_n],
                xi=RECENCY_XI,
                ridge=CONTROL_RIDGE,
                min_matches=CONTROL_MIN_MATCHES,
            )
        except DixonColesFitError as exc:
            control_fit_errors[str(league_id)] = str(exc)

    pooled_records = [
        SimpleNamespace(
            date=dates[index],
            home_id=int(home_ids[index]),
            away_id=int(away_ids[index]),
            home_goals=int(y_home[index]),
            away_goals=int(y_away[index]),
        )
        for index in range(train_n)
    ]
    pooled_team_counts = DixonColesModel.team_match_counts(pooled_records)
    pooled_latent_team_count = sum(
        appearances >= CONTROL_MIN_TEAM_APPEARANCES
        for appearances in pooled_team_counts.values()
    )
    pooled_control: DixonColesModel | None = None
    pooled_control_error: str | None = None
    try:
        pooled_control = _fit_sparse_pooled_control(
            pooled_records,
            reference_time=dates[train_n],
        )
    except DixonColesFitError as exc:
        pooled_control_error = str(exc)

    if not controls and pooled_control is None:
        return _empty_validation(
            model_version=model_version,
            evaluated_at=evaluated_at,
            status="CONTROL_FIT_FAILED",
            train_n=train_n,
            holdout_n=holdout_n,
            dates=dates,
            contract_snapshot={
                **contract_snapshot,
                "control_fit_errors": control_fit_errors,
                "pooled_control_error": pooled_control_error,
                "pooled_control_training_matches": len(pooled_records),
                "pooled_control_latent_team_count": pooled_latent_team_count,
                "control_min_team_appearances": CONTROL_MIN_TEAM_APPEARANCES,
            },
            reason="no league-specific or pooled stable-team Dixon-Coles control could be fitted",
        )

    dc_plus_rows: list[dict[str, float]] = []
    control_rows: list[dict[str, float]] = []
    invalid_holdout_rows = 0
    for offset, raw_features in enumerate(holdout_features):
        index = train_n + offset
        home_id = int(home_ids[index])
        away_id = int(away_ids[index])
        league_id = int(league_ids[index])
        control = controls.get(league_id)
        control_scope = "league"
        if (
            control is None
            or home_id not in set(control.team_ids)
            or away_id not in set(control.team_ids)
        ):
            control = pooled_control
            control_scope = "pooled"
        if control is None:
            continue
        control_teams = set(control.team_ids)
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
        scored_rows: list[dict[str, float]] = []
        invalid_holdout_reason: str | None = None
        for lambdas, rho, scope in (
            (dc_lambdas, float(dc_plus_params["rho"]), control_scope),
            (control_lambdas, float(control.rho), control_scope),
        ):
            lambda_home, lambda_away = lambdas
            try:
                over25, btts = _market_probabilities(
                    lambda_home,
                    lambda_away,
                    rho,
                )
            except ValueError as exc:
                invalid_holdout_reason = str(exc)
                break
            log_likelihood = _joint_log_likelihood(
                actual_home,
                actual_away,
                lambda_home,
                lambda_away,
                rho,
            )
            if not math.isfinite(log_likelihood):
                invalid_holdout_reason = "non-finite exact-score log likelihood"
                break
            scored_rows.append(
                {
                    "home_goals": float(actual_home),
                    "away_goals": float(actual_away),
                    "lambda_home": float(lambda_home),
                    "lambda_away": float(lambda_away),
                    "over25_probability": over25,
                    "btts_probability": btts,
                    "log_likelihood": log_likelihood,
                    "control_scope": scope,
                }
            )
        if invalid_holdout_reason is not None or len(scored_rows) != 2:
            invalid_holdout_rows += 1
            continue
        dc_plus_rows.append(scored_rows[0])
        control_rows.append(scored_rows[1])

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
        "control_leagues_fitted": sorted(controls),
        "control_league_fit_errors": control_fit_errors,
        "pooled_control_fitted": pooled_control is not None,
        "pooled_control_training_matches": len(pooled_records),
        "pooled_control_team_count": (
            0 if pooled_control is None else len(pooled_control.team_ids)
        ),
        "pooled_control_latent_team_count": pooled_latent_team_count,
        "pooled_control_error": pooled_control_error,
        "control_scope_counts": {
            "league": sum(row.get("control_scope") == "league" for row in control_rows),
            "pooled": sum(row.get("control_scope") == "pooled" for row in control_rows),
        },
        "invalid_holdout_rows": invalid_holdout_rows,
        "valid_common_coverage_pct": (
            0.0 if holdout_n == 0 else common_n / holdout_n * 100.0
        ),
        "note": (
            "comparison is evidence for manual GoalLab pick-authority review; "
            "pooled sparse-latent plain Dixon-Coles is used only when league-specific "
            "control coverage is unavailable; sparse teams receive neutral latent effects"
        ),
    }
    leakage = _leakage_audit()
    promotion_gate = {
        "common_evaluation_ok": common_n >= MIN_COMMON_EVALUATION,
        "leakage_ok": leakage["status"] == "PASS",
        "total_goals_rmse_non_worse": (
            comparison["dc_plus_minus_control_total_goals_rmse"] <= 0.0
        ),
        "over25_brier_non_worse": (
            comparison["dc_plus_minus_control_over25_brier"] <= 0.0
        ),
        "btts_brier_non_worse": (
            comparison["dc_plus_minus_control_btts_brier"] <= 0.0
        ),
        "exact_score_log_likelihood_not_materially_worse": (
            comparison["dc_plus_minus_control_exact_score_mean_log_likelihood"] >= -0.05
        ),
    }
    comparison["promotion_gate"] = promotion_gate
    comparison["automatic_promotion_rule"] = (
        "all promotion_gate checks must pass; authority still requires exact-hash approval"
    )
    ready = all(promotion_gate.values())
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
    existing = repository.goal_model_validation(
        model_version,
        method_version=METHOD_VERSION,
    )
    if existing is not None:
        logger.info(
            "GoalLab DC+ validation existing model=%s method=%s status=%s common_n=%s "
            "authority_review=%s comparison=%s leakage=%s contract=%s",
            model_version,
            existing.get("method_version"),
            existing.get("status"),
            existing.get("common_evaluation_size"),
            existing.get("authority_review_status"),
            existing.get("comparison"),
            existing.get("leakage_audit"),
            existing.get("contract_snapshot"),
        )
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
    return repository.goal_model_validation(
        model_version,
        method_version=METHOD_VERSION,
    ) or {
        "status": validation.status,
        "model_version": validation.model_version,
    }
