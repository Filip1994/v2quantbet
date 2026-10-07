"""Pure KellyLab sizing and point-in-time Research calibration math."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


KELLYLAB_CONTRACT_VERSION = "KELLYLAB_RESEARCH_V1"
KELLY_FRACTION = Decimal("0.25")
MAX_BET_FRACTION = Decimal("0.01")
CALIBRATION_PRIOR_N = 100


def probability_bucket(value: Any) -> str:
    p = float(value)
    pct = p * 100
    for low, high in ((40, 45), (45, 50), (50, 55), (55, 60), (60, 65), (65, 70), (70, 75)):
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 75:
        return "75%+"
    return "<40%"


def edge_bucket(value: Any) -> str:
    edge = float(value)
    pct = edge * 100
    for low, high in ((0, 5), (5, 10), (10, 15), (15, 20), (20, 30)):
        if low <= pct < high:
            return f"{low}–{high}%"
    if pct >= 30:
        return "30%+"
    return "<0%"


def odds_bucket(value: Any) -> str:
    odds = float(value)
    for low, high, label in (
        (1.40, 1.60, "1.40–1.60"),
        (1.60, 1.80, "1.61–1.80"),
        (1.80, 2.00, "1.81–2.00"),
        (2.00, 2.50, "2.01–2.50"),
        (2.50, 3.00, "2.51–3.00"),
        (3.00, 3.50, "3.01–3.50"),
    ):
        if low <= odds <= high:
            return label
    return "other"


def row_outcome(row: dict[str, Any]) -> str:
    classification = str(row.get("result_classification") or "")
    if classification == "NON_PLAYED_VOIDABLE":
        return "VOID"
    if classification != "PLAYED_SETTLEABLE":
        return "PENDING"

    home = row.get("regulation_home_goals")
    away = row.get("regulation_away_goals")
    if home is None or away is None:
        return "PENDING"

    home_goals = int(home)
    away_goals = int(away)
    market = str(row.get("market") or row.get("market_key") or "").upper()
    selection = str(row.get("selection") or "").upper()

    if market == "OU_25":
        over = home_goals + away_goals > 2
        won = over if selection == "OVER" else not over
    elif market == "BTTS":
        yes = home_goals > 0 and away_goals > 0
        won = yes if selection == "YES" else not yes
    else:
        return "PENDING"
    return "WIN" if won else "LOSS"


def _dimension_specs(row: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    market = str(row.get("market") or row.get("market_key") or "").upper()
    selection = str(row.get("selection") or "").upper()
    return (
        ("market_selection", f"{market}:{selection}"),
        ("model_probability_bucket", probability_bucket(row["model_probability"])),
        ("edge_bucket", edge_bucket(row["edge"])),
        ("odds_bucket", odds_bucket(row["odds"])),
    )


def _matches_dimension(
    row: dict[str, Any],
    dimension: str,
    value: str,
) -> bool:
    market = str(row.get("market") or row.get("market_key") or "").upper()
    selection = str(row.get("selection") or "").upper()
    if dimension == "market_selection":
        return f"{market}:{selection}" == value
    if dimension == "model_probability_bucket":
        return probability_bucket(row["model_probability"]) == value
    if dimension == "edge_bucket":
        return edge_bucket(row["edge"]) == value
    if dimension == "odds_bucket":
        return odds_bucket(row["odds"]) == value
    raise ValueError(f"unsupported KellyLab calibration dimension {dimension!r}")


def calibration_snapshot(
    candidate: dict[str, Any],
    prior_rows: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    *,
    prior_n: int = CALIBRATION_PRIOR_N,
) -> dict[str, Any]:
    """Build a deterministic point-in-time calibration snapshot.

    Each Research cohort contributes its observed-minus-model calibration gap.
    The gap is shrunk toward zero by N/(N+prior_n), then all available
    cohort contributions are averaged. Only WIN/LOSS rows are calibration-grade.
    """
    if prior_n <= 0:
        raise ValueError("prior_n must be positive")

    dimensions: list[dict[str, Any]] = []
    contributions: list[float] = []

    for dimension, value in _dimension_specs(candidate):
        cohort = [
            row
            for row in prior_rows
            if row_outcome(row) in {"WIN", "LOSS"}
            and _matches_dimension(row, dimension, value)
        ]
        n = len(cohort)
        if not n:
            dimensions.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "n": 0,
                    "win_rate": None,
                    "avg_model_probability": None,
                    "calibration_gap": None,
                    "shrinkage": 0.0,
                    "contribution": 0.0,
                }
            )
            continue

        wins = sum(row_outcome(row) == "WIN" for row in cohort)
        win_rate = wins / n
        avg_model = sum(float(row["model_probability"]) for row in cohort) / n
        gap = win_rate - avg_model
        shrinkage = n / (n + prior_n)
        contribution = gap * shrinkage
        contributions.append(contribution)
        dimensions.append(
            {
                "dimension": dimension,
                "value": value,
                "n": n,
                "win_rate": win_rate,
                "avg_model_probability": avg_model,
                "calibration_gap": gap,
                "shrinkage": shrinkage,
                "contribution": contribution,
            }
        )

    combined_gap = sum(contributions) / len(contributions) if contributions else 0.0
    model_probability = float(candidate["model_probability"])
    kelly_probability = min(0.99, max(0.01, model_probability + combined_gap))
    return {
        "version": "KELLYLAB_BUCKET_CALIBRATION_V1",
        "prior_n": prior_n,
        "model_probability": model_probability,
        "combined_calibration_gap": combined_gap,
        "kelly_probability": kelly_probability,
        "dimensions": dimensions,
    }


def raw_kelly_fraction(*, odds: Any, probability: Any) -> Decimal:
    odd = Decimal(str(odds))
    p = Decimal(str(probability))
    if not odd.is_finite() or odd <= 1:
        raise ValueError("odds must be finite and greater than one")
    if not p.is_finite() or p <= 0 or p >= 1:
        raise ValueError("probability must be between zero and one")
    value = ((odd * p) - Decimal(1)) / (odd - Decimal(1))
    return max(Decimal(0), value)


def kelly_stake_plan(
    *,
    bankroll_minor: int,
    odds: Any,
    probability: Any,
    kelly_fraction: Decimal = KELLY_FRACTION,
    max_bet_fraction: Decimal = MAX_BET_FRACTION,
) -> dict[str, Any]:
    if isinstance(bankroll_minor, bool) or not isinstance(bankroll_minor, int) or bankroll_minor <= 0:
        raise ValueError("bankroll_minor must be a positive integer")
    if kelly_fraction <= 0 or kelly_fraction > 1:
        raise ValueError("kelly_fraction must be in (0, 1]")
    if max_bet_fraction <= 0 or max_bet_fraction > 1:
        raise ValueError("max_bet_fraction must be in (0, 1]")

    raw = raw_kelly_fraction(odds=odds, probability=probability)
    fractional = raw * kelly_fraction
    applied = min(fractional, max_bet_fraction)
    stake = int(
        (Decimal(bankroll_minor) * applied).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )
    if raw <= 0 or stake <= 0:
        stake = 0
        applied = Decimal(0)
    return {
        "raw_kelly_fraction": raw,
        "fractional_kelly_fraction": fractional,
        "applied_kelly_fraction": applied,
        "stake_minor": stake,
        "decision": "BET" if stake > 0 else "NO_BET",
    }


def pnl_minor(*, stake_minor: int, odds: Any, outcome: str) -> int | None:
    if outcome == "PENDING":
        return None
    if outcome == "VOID":
        return 0
    if outcome == "LOSS":
        return -stake_minor
    if outcome != "WIN":
        raise ValueError(f"unsupported outcome {outcome!r}")
    odd = Decimal(str(odds))
    return int(
        (Decimal(stake_minor) * (odd - Decimal(1))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )
