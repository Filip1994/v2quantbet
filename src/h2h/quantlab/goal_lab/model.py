"""GoalLab DC+ Pro Structural V1.

This model keeps Dixon-Coles score semantics (two goal intensities plus rho low-score
correction) and learns regularized pre-match structural covariate offsets. Bookmaker
prices, provider predictions, target-match live statistics and post-kickoff facts are not
model features.

The feature builder is chronological: every training target is built only from earlier
completed matches in the supplied history. Missing values remain explicit and receive
missing-indicator features; zero is never used as a missing-value convention.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import exp, isfinite
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

from h2h.quant.dixon_coles import dixon_coles_tau


FEATURE_VERSION = "GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1"
MODEL_NAME = "DC+ Pro Structural"
MODEL_PREFIX = "DC_PLUS_PRO_STRUCTURAL_V1:"
RIDGE_TEAM = 1.5
RIDGE_FEATURE = 4.0
RIDGE_INTERACTION = 8.0
RECENCY_XI = 0.0015
MIN_TEAM_HISTORY = 5
MIN_TRAINING_EXAMPLES = 300
MIN_FEATURE_OBSERVATIONS = 20
HISTORY_LIMIT = 10_000

_RESULT_METRICS = (
    "goals_for",
    "goals_against",
    "ppg",
    "win",
    "draw",
    "clean_sheet",
    "failed_to_score",
    "btts",
    "over25",
)
_PRESSURE_METRICS = (
    "shots_for",
    "shots_against",
    "sot_for",
    "sot_against",
    "blocked_for",
    "inside_box_for",
    "outside_box_for",
    "corners_for",
    "corners_against",
    "possession",
    "offsides_for",
    "saves",
    "passes",
    "accurate_passes",
    "pass_accuracy",
    "fouls",
    "yellow_cards",
    "red_cards",
    "shot_share",
    "sot_share",
    "finishing_conversion",
    "save_proxy",
    "possession_adjusted_shots",
    "possession_adjusted_sot",
    "territorial_proxy",
    "set_piece_pressure",
)
_VENUE_METRICS = (
    "goals_for",
    "goals_against",
    "ppg",
    "clean_sheet",
    "failed_to_score",
    "shots_for",
    "sot_for",
    "possession",
    "corners_for",
    "corners_against",
)
_SEASON_METRICS = (
    "goals_for",
    "goals_against",
    "ppg",
    "win",
    "clean_sheet",
    "failed_to_score",
    "shots_for",
    "shots_against",
    "sot_for",
    "sot_against",
    "possession",
    "corners_for",
    "corners_against",
    "pass_accuracy",
)


@dataclass(frozen=True, slots=True)
class TeamMatchSample:
    fixture_id: str
    fixture_observation_id: str | None
    statistics_observation_id: str | None
    fixture_available_at: datetime | None
    statistics_available_at: datetime | None
    kickoff_at: datetime
    venue: str
    opponent_id: int
    season: int
    league_id: int
    values: dict[str, float | None]


@dataclass(frozen=True, slots=True)
class PairMatchSample:
    kickoff_at: datetime
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int


@dataclass(frozen=True, slots=True)
class GoalStructuralModelArtifact:
    model_version: str
    trained_at: datetime
    training_cutoff: datetime
    feature_version: str
    training_sample_size: int
    history_match_count: int
    team_count: int
    league_count: int
    ridge_team: float
    ridge_feature: float
    rho: float
    intercept: float
    home_advantage: float
    parameters: dict[str, Any]
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    training_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GoalFeatureSnapshot:
    fixture_id: str
    decision_at: datetime
    model_version: str
    expected_home_goals: float
    expected_away_goals: float
    home_history_size: int
    away_history_size: int
    feature_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GoalStructuralEstimate:
    expected_home_goals: float
    expected_away_goals: float
    model: GoalStructuralModelArtifact
    snapshot: GoalFeatureSnapshot

    def market_probabilities(self, max_goals: int = 10) -> dict[str, float]:
        matrix = _score_matrix(
            self.expected_home_goals,
            self.expected_away_goals,
            self.model.rho,
            max_goals=max_goals,
        )
        under = sum(
            float(matrix[h, a])
            for h in range(matrix.shape[0])
            for a in range(matrix.shape[1])
            if h + a <= 2
        )
        btts = float(matrix[1:, 1:].sum())
        return {
            "OVER_2_5": 1.0 - under,
            "UNDER_2_5": under,
            "BTTS_YES": btts,
        }


@dataclass(frozen=True, slots=True)
class GoalStructuralEstimateResult:
    estimate: GoalStructuralEstimate | None
    reason: str
    details: dict[str, Any]


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _safe_id(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _json_hash(payload: object) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _sample_values(
    *,
    goals_for: int,
    goals_against: int,
    shots_for: float | None,
    shots_against: float | None,
    sot_for: float | None,
    sot_against: float | None,
    blocked_for: float | None,
    inside_box_for: float | None,
    outside_box_for: float | None,
    corners_for: float | None,
    corners_against: float | None,
    possession: float | None,
    offsides_for: float | None,
    saves: float | None,
    passes: float | None,
    accurate_passes: float | None,
    pass_accuracy: float | None,
    fouls: float | None,
    yellow_cards: float | None,
    red_cards: float | None,
) -> dict[str, float | None]:
    total_goals = goals_for + goals_against
    points = 3.0 if goals_for > goals_against else 1.0 if goals_for == goals_against else 0.0
    shot_share = (
        None
        if shots_for is None or shots_against is None or shots_for + shots_against <= 0
        else shots_for / (shots_for + shots_against)
    )
    sot_share = (
        None
        if sot_for is None or sot_against is None or sot_for + sot_against <= 0
        else sot_for / (sot_for + sot_against)
    )
    finishing = _ratio(float(goals_for), sot_for)
    save_proxy = (
        None
        if saves is None or goals_against < 0 or saves + goals_against <= 0
        else saves / (saves + goals_against)
    )
    possession_fraction = (
        None if possession is None else possession / 100.0 if possession > 1.5 else possession
    )
    poss_adj_shots = (
        None
        if shots_for is None or possession_fraction is None or possession_fraction <= 0
        else shots_for / possession_fraction
    )
    poss_adj_sot = (
        None
        if sot_for is None or possession_fraction is None or possession_fraction <= 0
        else sot_for / possession_fraction
    )
    territorial = (
        None
        if shot_share is None or possession_fraction is None
        else 0.5 * shot_share + 0.5 * possession_fraction
    )
    set_piece_pressure = (
        None
        if corners_for is None and inside_box_for is None
        else float(corners_for or 0.0) + float(inside_box_for or 0.0)
    )
    return {
        "goals_for": float(goals_for),
        "goals_against": float(goals_against),
        "ppg": points,
        "win": float(goals_for > goals_against),
        "draw": float(goals_for == goals_against),
        "clean_sheet": float(goals_against == 0),
        "failed_to_score": float(goals_for == 0),
        "btts": float(goals_for > 0 and goals_against > 0),
        "over25": float(total_goals >= 3),
        "shots_for": shots_for,
        "shots_against": shots_against,
        "sot_for": sot_for,
        "sot_against": sot_against,
        "blocked_for": blocked_for,
        "inside_box_for": inside_box_for,
        "outside_box_for": outside_box_for,
        "corners_for": corners_for,
        "corners_against": corners_against,
        "possession": possession_fraction,
        "offsides_for": offsides_for,
        "saves": saves,
        "passes": passes,
        "accurate_passes": accurate_passes,
        "pass_accuracy": pass_accuracy,
        "fouls": fouls,
        "yellow_cards": yellow_cards,
        "red_cards": red_cards,
        "shot_share": shot_share,
        "sot_share": sot_share,
        "finishing_conversion": finishing,
        "save_proxy": save_proxy,
        "possession_adjusted_shots": poss_adj_shots,
        "possession_adjusted_sot": poss_adj_sot,
        "territorial_proxy": territorial,
        "set_piece_pressure": set_piece_pressure,
    }


def _team_samples(row: dict[str, Any]) -> tuple[TeamMatchSample, TeamMatchSample] | None:
    home_id = _safe_id(row.get("home_team_id"))
    away_id = _safe_id(row.get("away_team_id"))
    home_goals = _safe_nonnegative_int(row.get("home_goals"))
    away_goals = _safe_nonnegative_int(row.get("away_goals"))
    season = _safe_id(row.get("season"))
    league_id = _safe_id(row.get("league_id"))
    kickoff = row.get("kickoff_at")
    if (
        home_id is None
        or away_id is None
        or season is None
        or league_id is None
        or home_id == away_id
        or home_goals is None
        or away_goals is None
        or not isinstance(kickoff, datetime)
    ):
        return None

    home_values = _sample_values(
        goals_for=home_goals,
        goals_against=away_goals,
        shots_for=_number(row.get("home_total_shots")),
        shots_against=_number(row.get("away_total_shots")),
        sot_for=_number(row.get("home_shots_on_goal")),
        sot_against=_number(row.get("away_shots_on_goal")),
        blocked_for=_number(row.get("home_blocked_shots")),
        inside_box_for=_number(row.get("home_shots_insidebox")),
        outside_box_for=_number(row.get("home_shots_outsidebox")),
        corners_for=_number(row.get("home_corner_kicks")),
        corners_against=_number(row.get("away_corner_kicks")),
        possession=_number(row.get("home_ball_possession")),
        offsides_for=_number(row.get("home_offsides")),
        saves=_number(row.get("home_goalkeeper_saves")),
        passes=_number(row.get("home_total_passes")),
        accurate_passes=_number(row.get("home_passes_accurate")),
        pass_accuracy=_number(row.get("home_pass_accuracy")),
        fouls=_number(row.get("home_fouls")),
        yellow_cards=_number(row.get("home_yellow_cards")),
        red_cards=_number(row.get("home_red_cards")),
    )
    away_values = _sample_values(
        goals_for=away_goals,
        goals_against=home_goals,
        shots_for=_number(row.get("away_total_shots")),
        shots_against=_number(row.get("home_total_shots")),
        sot_for=_number(row.get("away_shots_on_goal")),
        sot_against=_number(row.get("home_shots_on_goal")),
        blocked_for=_number(row.get("away_blocked_shots")),
        inside_box_for=_number(row.get("away_shots_insidebox")),
        outside_box_for=_number(row.get("away_shots_outsidebox")),
        corners_for=_number(row.get("away_corner_kicks")),
        corners_against=_number(row.get("home_corner_kicks")),
        possession=_number(row.get("away_ball_possession")),
        offsides_for=_number(row.get("away_offsides")),
        saves=_number(row.get("away_goalkeeper_saves")),
        passes=_number(row.get("away_total_passes")),
        accurate_passes=_number(row.get("away_passes_accurate")),
        pass_accuracy=_number(row.get("away_pass_accuracy")),
        fouls=_number(row.get("away_fouls")),
        yellow_cards=_number(row.get("away_yellow_cards")),
        red_cards=_number(row.get("away_red_cards")),
    )
    fixture_id = str(row.get("fixture_id") or "")
    fixture_observation_id = (
        None
        if row.get("fixture_observation_id") is None
        else str(row["fixture_observation_id"])
    )
    statistics_observation_id = (
        None
        if row.get("statistics_observation_id") is None
        else str(row["statistics_observation_id"])
    )
    fixture_available_at = row.get("fixture_available_at")
    statistics_available_at = row.get("statistics_available_at")
    return (
        TeamMatchSample(
            fixture_id,
            fixture_observation_id,
            statistics_observation_id,
            fixture_available_at if isinstance(fixture_available_at, datetime) else None,
            statistics_available_at
            if isinstance(statistics_available_at, datetime)
            else None,
            kickoff.astimezone(UTC),
            "HOME",
            away_id,
            season,
            league_id,
            home_values,
        ),
        TeamMatchSample(
            fixture_id,
            fixture_observation_id,
            statistics_observation_id,
            fixture_available_at if isinstance(fixture_available_at, datetime) else None,
            statistics_available_at
            if isinstance(statistics_available_at, datetime)
            else None,
            kickoff.astimezone(UTC),
            "AWAY",
            home_id,
            season,
            league_id,
            away_values,
        ),
    )


def _safe_nonnegative_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _mean(
    samples: list[TeamMatchSample],
    metric: str,
    *,
    count: int | None = None,
    venue: str | None = None,
) -> float:
    eligible = samples if venue is None else [item for item in samples if item.venue == venue]
    if count is not None:
        eligible = eligible[-count:]
    values = [value for item in eligible if (value := item.values.get(metric)) is not None]
    return float("nan") if not values else float(sum(values) / len(values))


def _team_feature_map(
    samples: list[TeamMatchSample],
    *,
    prefix: str,
    venue: str,
    target_kickoff: datetime,
    target_season: int,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for window in (3, 5, 10):
        for metric in _RESULT_METRICS:
            result[f"{prefix}_l{window}_{metric}"] = _mean(samples, metric, count=window)
    for window in (5, 10):
        for metric in _PRESSURE_METRICS:
            result[f"{prefix}_l{window}_{metric}"] = _mean(samples, metric, count=window)
    for metric in _VENUE_METRICS:
        result[f"{prefix}_venue_l5_{metric}"] = _mean(
            samples, metric, count=5, venue=venue
        )
    season_samples = [item for item in samples if item.season == target_season]
    for metric in _SEASON_METRICS:
        result[f"{prefix}_season_{metric}"] = _mean(season_samples, metric)

    result[f"{prefix}_history_match_count"] = float(len(samples))
    result[f"{prefix}_season_match_count"] = float(len(season_samples))

    if samples:
        last_kickoff = samples[-1].kickoff_at
        rest_days = max(0.0, (target_kickoff - last_kickoff).total_seconds() / 86_400.0)
        result[f"{prefix}_rest_days"] = rest_days
        for days in (7, 14, 21):
            cutoff = target_kickoff.timestamp() - days * 86_400.0
            result[f"{prefix}_matches_last_{days}d"] = float(
                sum(item.kickoff_at.timestamp() >= cutoff for item in samples)
            )
    else:
        result[f"{prefix}_rest_days"] = float("nan")
        for days in (7, 14, 21):
            result[f"{prefix}_matches_last_{days}d"] = float("nan")
    return result


def _h2h_features(
    pairs: list[PairMatchSample],
    home_id: int,
    away_id: int,
    target_kickoff: datetime,
) -> dict[str, float]:
    relevant = [
        item
        for item in pairs
        if {item.home_id, item.away_id} == {home_id, away_id}
        and item.kickoff_at < target_kickoff
    ][-5:]
    if not relevant:
        return {
            "h2h_goals_per_match_l5": float("nan"),
            "h2h_btts_rate_l5": float("nan"),
            "h2h_over25_rate_l5": float("nan"),
            "h2h_target_home_goals_l5": float("nan"),
            "h2h_target_away_goals_l5": float("nan"),
            "h2h_goal_difference_l5": float("nan"),
            "h2h_sample_size": 0.0,
            "h2h_age_days": float("nan"),
        }

    home_scored: list[float] = []
    away_scored: list[float] = []
    totals: list[float] = []
    btts: list[float] = []
    over25: list[float] = []
    for item in relevant:
        if item.home_id == home_id:
            hg, ag = item.home_goals, item.away_goals
        else:
            hg, ag = item.away_goals, item.home_goals
        home_scored.append(float(hg))
        away_scored.append(float(ag))
        totals.append(float(hg + ag))
        btts.append(float(hg > 0 and ag > 0))
        over25.append(float(hg + ag >= 3))
    age_days = max(
        0.0, (target_kickoff - relevant[-1].kickoff_at).total_seconds() / 86_400.0
    )
    return {
        "h2h_goals_per_match_l5": float(np.mean(totals)),
        "h2h_btts_rate_l5": float(np.mean(btts)),
        "h2h_over25_rate_l5": float(np.mean(over25)),
        "h2h_target_home_goals_l5": float(np.mean(home_scored)),
        "h2h_target_away_goals_l5": float(np.mean(away_scored)),
        "h2h_goal_difference_l5": float(np.mean(np.asarray(home_scored) - np.asarray(away_scored))),
        "h2h_sample_size": float(len(relevant)),
        "h2h_age_days": age_days,
    }


def _binary_op(a: float | None, b: float | None, op: str) -> float:
    if a is None or b is None or not isfinite(a) or not isfinite(b):
        return float("nan")
    if op == "diff":
        return a - b
    if op == "product":
        return a * b
    raise ValueError(op)


def _feature_map(
    histories: dict[int, list[TeamMatchSample]],
    pairs: list[PairMatchSample],
    *,
    home_id: int,
    away_id: int,
    target_kickoff: datetime,
    target_season: int,
) -> dict[str, float]:
    home = _team_feature_map(
        histories.get(home_id, []),
        prefix="home",
        venue="HOME",
        target_kickoff=target_kickoff,
        target_season=target_season,
    )
    away = _team_feature_map(
        histories.get(away_id, []),
        prefix="away",
        venue="AWAY",
        target_kickoff=target_kickoff,
        target_season=target_season,
    )
    features = {**home, **away, **_h2h_features(pairs, home_id, away_id, target_kickoff)}

    features["matchup_goal_attack_x_defence_home"] = _binary_op(
        features.get("home_l5_goals_for"),
        features.get("away_l5_goals_against"),
        "product",
    )
    features["matchup_goal_attack_x_defence_away"] = _binary_op(
        features.get("away_l5_goals_for"),
        features.get("home_l5_goals_against"),
        "product",
    )
    features["matchup_sot_x_sot_allowed_home"] = _binary_op(
        features.get("home_l5_sot_for"),
        features.get("away_l5_sot_against"),
        "product",
    )
    features["matchup_sot_x_sot_allowed_away"] = _binary_op(
        features.get("away_l5_sot_for"),
        features.get("home_l5_sot_against"),
        "product",
    )
    features["matchup_finishing_x_save_home"] = _binary_op(
        features.get("home_l5_finishing_conversion"),
        features.get("away_l5_save_proxy"),
        "product",
    )
    features["matchup_finishing_x_save_away"] = _binary_op(
        features.get("away_l5_finishing_conversion"),
        features.get("home_l5_save_proxy"),
        "product",
    )
    features["home_away_goal_form_diff"] = _binary_op(
        features.get("home_l5_goals_for"), features.get("away_l5_goals_for"), "diff"
    )
    features["home_away_sot_diff"] = _binary_op(
        features.get("home_l5_sot_for"), features.get("away_l5_sot_for"), "diff"
    )
    features["home_away_possession_diff"] = _binary_op(
        features.get("home_l5_possession"), features.get("away_l5_possession"), "diff"
    )
    features["home_away_corner_diff"] = _binary_op(
        features.get("home_l5_corners_for"), features.get("away_l5_corners_for"), "diff"
    )
    features["rest_day_differential"] = _binary_op(
        features.get("home_rest_days"), features.get("away_rest_days"), "diff"
    )
    features["congestion_14d_differential"] = _binary_op(
        features.get("home_matches_last_14d"),
        features.get("away_matches_last_14d"),
        "diff",
    )
    return features


def _build_training(
    rows: tuple[dict[str, Any], ...],
) -> tuple[
    list[dict[str, float]],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[int, list[TeamMatchSample]],
    list[PairMatchSample],
    int,
]:
    histories: dict[int, list[TeamMatchSample]] = {}
    pairs: list[PairMatchSample] = []
    feature_rows: list[dict[str, float]] = []
    home_targets: list[float] = []
    away_targets: list[float] = []
    home_ids: list[int] = []
    away_ids: list[int] = []
    league_ids: list[int] = []
    dates: list[datetime] = []
    usable_matches = 0

    ordered = sorted(
        rows,
        key=lambda row: (
            row.get("kickoff_at") or datetime.min.replace(tzinfo=UTC),
            str(row.get("fixture_id") or ""),
        ),
    )
    for row in ordered:
        home_id = _safe_id(row.get("home_team_id"))
        away_id = _safe_id(row.get("away_team_id"))
        league_id = _safe_id(row.get("league_id"))
        home_goals = _safe_nonnegative_int(row.get("home_goals"))
        away_goals = _safe_nonnegative_int(row.get("away_goals"))
        kickoff = row.get("kickoff_at")
        samples = _team_samples(row)
        if (
            home_id is None
            or away_id is None
            or league_id is None
            or home_id == away_id
            or home_goals is None
            or away_goals is None
            or not isinstance(kickoff, datetime)
            or samples is None
        ):
            continue
        kickoff = kickoff.astimezone(UTC)
        usable_matches += 1
        home_history = histories.setdefault(home_id, [])
        away_history = histories.setdefault(away_id, [])

        if len(home_history) >= MIN_TEAM_HISTORY and len(away_history) >= MIN_TEAM_HISTORY:
            feature_rows.append(
                _feature_map(
                    histories,
                    pairs,
                    home_id=home_id,
                    away_id=away_id,
                    target_kickoff=kickoff,
                    target_season=int(row["season"]),
                )
            )
            home_targets.append(float(home_goals))
            away_targets.append(float(away_goals))
            home_ids.append(home_id)
            away_ids.append(away_id)
            league_ids.append(league_id)
            dates.append(kickoff)

        home_sample, away_sample = samples
        home_history.append(home_sample)
        away_history.append(away_sample)
        pairs.append(
            PairMatchSample(kickoff, home_id, away_id, home_goals, away_goals)
        )

    return (
        feature_rows,
        np.asarray(home_targets, dtype=float),
        np.asarray(away_targets, dtype=float),
        np.asarray(home_ids, dtype=np.int64),
        np.asarray(away_ids, dtype=np.int64),
        np.asarray(league_ids, dtype=np.int64),
        np.asarray(dates, dtype=object),
        histories,
        pairs,
        usable_matches,
    )


def _prepare_features(
    rows: list[dict[str, float]],
) -> tuple[np.ndarray, tuple[str, ...], dict[str, float], dict[str, float], tuple[str, ...]]:
    if not rows:
        return np.empty((0, 0)), (), {}, {}, ()
    candidate_names = tuple(sorted({name for row in rows for name in row}))
    raw = np.asarray(
        [[row.get(name, float("nan")) for name in candidate_names] for row in rows],
        dtype=float,
    )
    observed = np.isfinite(raw)
    keep = np.sum(observed, axis=0) >= MIN_FEATURE_OBSERVATIONS
    base_names = tuple(name for name, ok in zip(candidate_names, keep, strict=True) if ok)
    raw = raw[:, keep]
    observed = observed[:, keep]
    if raw.shape[1] == 0:
        return np.empty((len(rows), 0)), (), {}, {}, ()

    means_arr = np.asarray(
        [
            float(np.mean(raw[observed[:, index], index]))
            for index in range(raw.shape[1])
        ],
        dtype=float,
    )
    imputed = np.where(observed, raw, means_arr)
    scales_arr = np.std(imputed, axis=0)
    scales_arr = np.where(scales_arr < 1e-8, 1.0, scales_arr)
    standardized = (imputed - means_arr) / scales_arr

    missing_names: list[str] = []
    missing_columns: list[np.ndarray] = []
    for index, name in enumerate(base_names):
        if not np.all(observed[:, index]):
            missing_names.append(f"{name}__missing")
            missing_columns.append((~observed[:, index]).astype(float))
    if missing_columns:
        x = np.column_stack([standardized, *missing_columns])
    else:
        x = standardized

    model_names = base_names + tuple(missing_names)
    means = {
        name: float(value)
        for name, value in zip(base_names, means_arr, strict=True)
    }
    scales = {
        name: float(value)
        for name, value in zip(base_names, scales_arr, strict=True)
    }
    return x, model_names, means, scales, base_names


def _transform_feature_row(
    row: dict[str, float],
    *,
    model_feature_names: tuple[str, ...],
    base_feature_names: tuple[str, ...],
    means: dict[str, float],
    scales: dict[str, float],
) -> tuple[np.ndarray, dict[str, float | None]]:
    values: list[float] = []
    raw_payload: dict[str, float | None] = {}
    missing_flags: dict[str, float] = {}
    for name in base_feature_names:
        raw = row.get(name, float("nan"))
        finite = isfinite(raw)
        raw_payload[name] = float(raw) if finite else None
        imputed = float(raw) if finite else means[name]
        values.append((imputed - means[name]) / scales[name])
        missing_flags[f"{name}__missing"] = 0.0 if finite else 1.0

    base_count = len(base_feature_names)
    result = list(values)
    for name in model_feature_names[base_count:]:
        result.append(missing_flags[name])
    return np.asarray(result, dtype=float), raw_payload


def _feature_penalties(names: tuple[str, ...]) -> np.ndarray:
    return np.asarray(
        [
            RIDGE_INTERACTION
            if name.startswith(("matchup_", "h2h_"))
            else RIDGE_FEATURE
            for name in names
        ],
        dtype=float,
    )


def _fit_dc_plus(
    x: np.ndarray,
    y_home: np.ndarray,
    y_away: np.ndarray,
    home_ids: np.ndarray,
    away_ids: np.ndarray,
    league_ids: np.ndarray,
    dates: np.ndarray,
    feature_names: tuple[str, ...],
    *,
    reference_time: datetime,
) -> tuple[dict[str, Any], float] | None:
    n = len(y_home)
    if n < MIN_TRAINING_EXAMPLES or x.shape[1] == 0:
        return None

    team_values = tuple(sorted(set(home_ids.tolist()) | set(away_ids.tolist())))
    league_values = tuple(sorted(set(league_ids.tolist())))
    team_index = {team_id: index for index, team_id in enumerate(team_values)}
    league_index = {league_id: index for index, league_id in enumerate(league_values)}
    h_idx = np.asarray([team_index[int(value)] for value in home_ids], dtype=np.int64)
    a_idx = np.asarray([team_index[int(value)] for value in away_ids], dtype=np.int64)
    l_idx = np.asarray([league_index[int(value)] for value in league_ids], dtype=np.int64)

    nt = len(team_values)
    nl = len(league_values)
    nf = x.shape[1]
    attack_slice = slice(0, nt)
    defense_slice = slice(nt, 2 * nt)
    league_slice = slice(2 * nt, 2 * nt + nl)
    intercept_index = 2 * nt + nl
    home_adv_index = intercept_index + 1
    rho_index = intercept_index + 2
    beta_home_slice = slice(rho_index + 1, rho_index + 1 + nf)
    beta_away_slice = slice(rho_index + 1 + nf, rho_index + 1 + 2 * nf)
    size = rho_index + 1 + 2 * nf

    mean_goal = max(0.2, float(np.mean(np.concatenate([y_home, y_away]))))
    initial = np.zeros(size, dtype=float)
    initial[intercept_index] = math.log(mean_goal)
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
    feature_penalty = _feature_penalties(feature_names)

    def objective(params: np.ndarray) -> tuple[float, np.ndarray]:
        attacks = params[attack_slice]
        defenses = params[defense_slice]
        leagues = params[league_slice]
        intercept = float(params[intercept_index])
        home_adv = float(params[home_adv_index])
        rho = float(params[rho_index])
        beta_home = params[beta_home_slice]
        beta_away = params[beta_away_slice]

        eta_home_raw = (
            intercept
            + home_adv
            + attacks[h_idx]
            + defenses[a_idx]
            + leagues[l_idx]
            + x @ beta_home
        )
        eta_away_raw = (
            intercept
            + attacks[a_idx]
            + defenses[h_idx]
            + leagues[l_idx]
            + x @ beta_away
        )
        eta_home = np.clip(eta_home_raw, -6.0, 4.0)
        eta_away = np.clip(eta_away_raw, -6.0, 4.0)
        lambda_home = np.exp(eta_home)
        lambda_away = np.exp(eta_away)

        tau = np.ones(n, dtype=float)
        dlogtau_home = np.zeros(n, dtype=float)
        dlogtau_away = np.zeros(n, dtype=float)
        dlogtau_rho = np.zeros(n, dtype=float)

        mask00 = (y_home == 0) & (y_away == 0)
        mask01 = (y_home == 0) & (y_away == 1)
        mask10 = (y_home == 1) & (y_away == 0)
        mask11 = (y_home == 1) & (y_away == 1)

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
            - y_home * eta_home
            + gammaln(y_home + 1.0)
            + lambda_away
            - y_away * eta_away
            + gammaln(y_away + 1.0)
            - np.log(tau)
        )

        penalties = (
            RIDGE_TEAM * (np.dot(attacks, attacks) + np.dot(defenses, defenses))
            + RIDGE_TEAM * np.dot(leagues, leagues)
            + float(np.dot(feature_penalty, beta_home * beta_home))
            + float(np.dot(feature_penalty, beta_away * beta_away))
        )
        value = float(np.dot(weights, neg_ll) + penalties)

        grad_eta_home = weights * (lambda_home - y_home - dlogtau_home)
        grad_eta_away = weights * (lambda_away - y_away - dlogtau_away)
        grad_eta_home *= ((eta_home_raw > -6.0) & (eta_home_raw < 4.0))
        grad_eta_away *= ((eta_away_raw > -6.0) & (eta_away_raw < 4.0))

        grad = np.zeros_like(params)
        np.add.at(grad[attack_slice], h_idx, grad_eta_home)
        np.add.at(grad[attack_slice], a_idx, grad_eta_away)
        np.add.at(grad[defense_slice], a_idx, grad_eta_home)
        np.add.at(grad[defense_slice], h_idx, grad_eta_away)
        np.add.at(grad[league_slice], l_idx, grad_eta_home + grad_eta_away)
        grad[intercept_index] = float(np.sum(grad_eta_home + grad_eta_away))
        grad[home_adv_index] = float(np.sum(grad_eta_home))
        grad[rho_index] = float(np.sum(weights * (-dlogtau_rho)))
        grad[beta_home_slice] = x.T @ grad_eta_home
        grad[beta_away_slice] = x.T @ grad_eta_away

        grad[attack_slice] += 2.0 * RIDGE_TEAM * attacks
        grad[defense_slice] += 2.0 * RIDGE_TEAM * defenses
        grad[league_slice] += 2.0 * RIDGE_TEAM * leagues
        grad[beta_home_slice] += 2.0 * feature_penalty * beta_home
        grad[beta_away_slice] += 2.0 * feature_penalty * beta_away
        return value, grad

    bounds = (
        [(-3.0, 3.0)] * nt
        + [(-3.0, 3.0)] * nt
        + [(-1.5, 1.5)] * nl
        + [(-2.0, 2.0), (-1.0, 1.0), (-0.20, 0.20)]
        + [(-2.0, 2.0)] * nf
        + [(-2.0, 2.0)] * nf
    )
    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        bounds=bounds,
        options={"maxiter": 700, "ftol": 1e-9, "gtol": 1e-6},
    )
    if not result.success or not np.isfinite(result.fun):
        return None

    params = result.x
    payload = {
        "team_ids": team_values,
        "league_ids": league_values,
        "attacks": {
            str(team_id): float(params[attack_slice][index])
            for index, team_id in enumerate(team_values)
        },
        "defenses": {
            str(team_id): float(params[defense_slice][index])
            for index, team_id in enumerate(team_values)
        },
        "league_effects": {
            str(league_id): float(params[league_slice][index])
            for index, league_id in enumerate(league_values)
        },
        "intercept": float(params[intercept_index]),
        "home_advantage": float(params[home_adv_index]),
        "rho": float(params[rho_index]),
        "beta_home": [float(value) for value in params[beta_home_slice]],
        "beta_away": [float(value) for value in params[beta_away_slice]],
    }
    return payload, float(result.fun)


def _score_matrix(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    *,
    max_goals: int = 10,
) -> np.ndarray:
    goals = np.arange(max_goals + 1)
    matrix = np.outer(poisson.pmf(goals, lambda_home), poisson.pmf(goals, lambda_away))
    for home_goals in (0, 1):
        for away_goals in (0, 1):
            correction = dixon_coles_tau(
                home_goals, away_goals, lambda_home, lambda_away, rho
            )
            if correction <= 0:
                raise ValueError("invalid DC+ rho correction")
            matrix[home_goals, away_goals] *= correction
    total = float(matrix.sum())
    if total <= 0 or not np.isfinite(total):
        raise ValueError("invalid DC+ score matrix")
    return matrix / total


class GoalStructuralModelService:
    """Fit once per decision timestamp and estimate DC+ goal intensities."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository
        self._cache_at: datetime | None = None
        self._artifact: GoalStructuralModelArtifact | None = None
        self._histories: dict[int, list[TeamMatchSample]] = {}
        self._pairs: list[PairMatchSample] = []
        self._fit_reason = "NOT_FITTED"
        self._fit_details: dict[str, Any] = {}

    def _prepare(self, decision_at: datetime) -> None:
        now = decision_at.astimezone(UTC)
        if self._cache_at == now:
            return
        rows = self._repository.goal_model_history(before=now, limit=HISTORY_LIMIT)
        (
            feature_rows,
            y_home,
            y_away,
            home_ids,
            away_ids,
            league_ids,
            dates,
            histories,
            pairs,
            history_match_count,
        ) = _build_training(rows)
        x, model_feature_names, means, scales, base_feature_names = _prepare_features(
            feature_rows
        )
        self._cache_at = now
        self._histories = histories
        self._pairs = pairs

        if len(y_home) < MIN_TRAINING_EXAMPLES or x.shape[1] == 0:
            self._artifact = None
            self._fit_reason = "INSUFFICIENT_GOAL_MODEL_HISTORY"
            self._fit_details = {
                "history_match_count": history_match_count,
                "training_sample_size": len(y_home),
                "minimum_training_examples": MIN_TRAINING_EXAMPLES,
                "active_feature_count": int(x.shape[1]),
            }
            return

        fitted = _fit_dc_plus(
            x,
            y_home,
            y_away,
            home_ids,
            away_ids,
            league_ids,
            dates,
            model_feature_names,
            reference_time=now,
        )
        if fitted is None:
            self._artifact = None
            self._fit_reason = "GOAL_MODEL_FIT_FAILED"
            self._fit_details = {
                "history_match_count": history_match_count,
                "training_sample_size": len(y_home),
                "active_feature_count": int(x.shape[1]),
            }
            return

        params, objective = fitted
        params["model_feature_names"] = model_feature_names
        params["base_feature_names"] = base_feature_names
        identity = {
            "feature_version": FEATURE_VERSION,
            "training_cutoff": now.isoformat(),
            "training_sample_size": len(y_home),
            "history_match_count": history_match_count,
            "ridge_team": RIDGE_TEAM,
            "ridge_feature": RIDGE_FEATURE,
            "ridge_interaction": RIDGE_INTERACTION,
            "recency_xi": RECENCY_XI,
            "parameters": params,
            "feature_means": means,
            "feature_scales": scales,
        }
        model_version = MODEL_PREFIX + _json_hash(identity)
        artifact = GoalStructuralModelArtifact(
            model_version=model_version,
            trained_at=now,
            training_cutoff=now,
            feature_version=FEATURE_VERSION,
            training_sample_size=len(y_home),
            history_match_count=history_match_count,
            team_count=len(params["team_ids"]),
            league_count=len(params["league_ids"]),
            ridge_team=RIDGE_TEAM,
            ridge_feature=RIDGE_FEATURE,
            rho=float(params["rho"]),
            intercept=float(params["intercept"]),
            home_advantage=float(params["home_advantage"]),
            parameters=params,
            feature_means=means,
            feature_scales=scales,
            training_payload={
                "objective": objective,
                "minimum_team_history": MIN_TEAM_HISTORY,
                "minimum_training_examples": MIN_TRAINING_EXAMPLES,
                "minimum_feature_observations": MIN_FEATURE_OBSERVATIONS,
                "history_limit": HISTORY_LIMIT,
                "recency_xi": RECENCY_XI,
                "structural_only": True,
                "bookmaker_features_used": False,
                "provider_predictions_used": False,
                "target_match_live_stats_used": False,
                "contract_blocks_active": [
                    "A_BASE_DC",
                    "B_RECENT_RESULT_GOAL_FORM",
                    "C_VENUE_FORM",
                    "D_SEASON_AGGREGATES",
                    "E_SHOT_PRODUCTION_PREVENTION",
                    "F_GOALKEEPER_FINISHING",
                    "G_POSSESSION_PASSING",
                    "H_SET_PIECES_TERRITORY",
                    "I_DISCIPLINE_HISTORICAL",
                    "J_REST_CONGESTION",
                    "P_H2H",
                    "R_MATCHUP_INTERACTIONS",
                    "MISSINGNESS",
                ],
                "contract_blocks_pending_acquisition": [
                    "K_STANDINGS_HISTORICAL",
                    "L_INJURY_SUSPENSION",
                    "M_TARGET_LINEUP_FORMATION",
                    "N_PLAYER_FORM_AGGREGATION",
                    "O_MANAGER_CONTEXT",
                    "Q_OPPONENT_ADJUSTED_FORM",
                ],
            },
        )
        self._repository.save_goal_model_version(artifact)
        self._artifact = artifact
        self._fit_reason = "MODEL_READY"
        self._fit_details = {
            "history_match_count": history_match_count,
            "training_sample_size": len(y_home),
            "active_feature_count": len(model_feature_names),
        }

    def estimate(
        self,
        fixture: dict[str, Any],
        *,
        decision_at: datetime,
    ) -> GoalStructuralEstimateResult:
        self._prepare(decision_at)
        if self._artifact is None:
            return GoalStructuralEstimateResult(
                None, self._fit_reason, dict(self._fit_details)
            )

        home_id = _safe_id(fixture.get("home_team_id"))
        away_id = _safe_id(fixture.get("away_team_id"))
        league_id = _safe_id(fixture.get("league_id"))
        kickoff = fixture.get("kickoff_at")
        if (
            home_id is None
            or away_id is None
            or home_id == away_id
            or league_id is None
            or not isinstance(kickoff, datetime)
        ):
            return GoalStructuralEstimateResult(
                None,
                "MISSING_GOAL_MODEL_DIMENSIONS",
                {
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                    "league_id": league_id,
                },
            )
        home_history = self._histories.get(home_id, [])
        away_history = self._histories.get(away_id, [])
        if len(home_history) < MIN_TEAM_HISTORY or len(away_history) < MIN_TEAM_HISTORY:
            return GoalStructuralEstimateResult(
                None,
                "INSUFFICIENT_TEAM_GOAL_HISTORY",
                {
                    "home_history_size": len(home_history),
                    "away_history_size": len(away_history),
                    "minimum_team_history": MIN_TEAM_HISTORY,
                },
            )

        params = self._artifact.parameters
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
            return GoalStructuralEstimateResult(
                None,
                "GOAL_MODEL_TEAM_OR_LEAGUE_UNCOVERED",
                {"home_team_id": home_id, "away_team_id": away_id, "league_id": league_id},
            )

        kickoff = kickoff.astimezone(UTC)
        raw_map = _feature_map(
            self._histories,
            self._pairs,
            home_id=home_id,
            away_id=away_id,
            target_kickoff=kickoff,
            target_season=int(fixture["season"]),
        )
        model_feature_names = tuple(params["model_feature_names"])
        base_feature_names = tuple(params["base_feature_names"])
        vector, raw_payload = _transform_feature_row(
            raw_map,
            model_feature_names=model_feature_names,
            base_feature_names=base_feature_names,
            means=self._artifact.feature_means,
            scales=self._artifact.feature_scales,
        )
        beta_home = np.asarray(params["beta_home"], dtype=float)
        beta_away = np.asarray(params["beta_away"], dtype=float)
        eta_home = (
            self._artifact.intercept
            + self._artifact.home_advantage
            + float(attacks[str(home_id)])
            + float(defenses[str(away_id)])
            + float(leagues[str(league_id)])
            + float(np.dot(vector, beta_home))
        )
        eta_away = (
            self._artifact.intercept
            + float(attacks[str(away_id)])
            + float(defenses[str(home_id)])
            + float(leagues[str(league_id)])
            + float(np.dot(vector, beta_away))
        )
        lambda_home = exp(max(-6.0, min(4.0, eta_home)))
        lambda_away = exp(max(-6.0, min(4.0, eta_away)))
        if not all(isfinite(value) and value > 0 for value in (lambda_home, lambda_away)):
            return GoalStructuralEstimateResult(
                None,
                "INVALID_GOAL_MODEL_OUTPUT",
                {"eta_home": eta_home, "eta_away": eta_away},
            )

        snapshot = GoalFeatureSnapshot(
            fixture_id=str(fixture["fixture_id"]),
            decision_at=decision_at.astimezone(UTC),
            model_version=self._artifact.model_version,
            expected_home_goals=lambda_home,
            expected_away_goals=lambda_away,
            home_history_size=len(home_history),
            away_history_size=len(away_history),
            feature_payload={
                "feature_version": FEATURE_VERSION,
                "raw_features": raw_payload,
                "model_feature_names": model_feature_names,
                "home_history_size": len(home_history),
                "away_history_size": len(away_history),
                "league_id": league_id,
                "rho": self._artifact.rho,
                "contract_blocks_pending_acquisition": self._artifact.training_payload[
                    "contract_blocks_pending_acquisition"
                ],
            },
        )
        self._repository.save_goal_feature_snapshot(snapshot)
        return GoalStructuralEstimateResult(
            GoalStructuralEstimate(
                expected_home_goals=lambda_home,
                expected_away_goals=lambda_away,
                model=self._artifact,
                snapshot=snapshot,
            ),
            "MODEL_READY",
            {
                "training_sample_size": self._artifact.training_sample_size,
                "history_match_count": self._artifact.history_match_count,
                "active_feature_count": len(model_feature_names),
            },
        )
