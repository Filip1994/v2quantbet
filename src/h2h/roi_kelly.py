"""Conservative ROI-driven Kelly sizing for existing CornerLab buckets.

Research-only estimator. Never sends orders, changes bankroll or mutates the
Production funnel. The bookmaker filter is mandatory and the probability
estimate is shrunk towards the current quote's break-even probability.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite

from scipy.stats import beta


MIN_GRADED_N = 31
PRIOR_EQUIVALENT_BETS = 40
LOWER_PROBABILITY_QUANTILE = 0.10
KELLY_MULTIPLIER = 0.25
MAX_BANKROLL_FRACTION = 0.01


@dataclass(frozen=True, slots=True)
class RoiKellyDecision:
    bucket_id: str
    graded_n: int
    wins: int
    losses: int
    historical_roi_pct: float
    quote_odds: float
    break_even_probability: float
    posterior_mean_probability: float
    conservative_probability: float
    conservative_roi_pct: float
    raw_kelly_fraction: float
    applied_fraction: float
    stake_minor: int
    decision: str
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def calculate_roi_kelly(
    *,
    bucket_id: str,
    wins: int,
    losses: int,
    historical_unit_pnl: float,
    quote_odds: float,
    bankroll_minor: int,
    verified_one_xbet: bool,
    min_graded_n: int = MIN_GRADED_N,
    prior_equivalent_bets: int = PRIOR_EQUIVALENT_BETS,
    lower_probability_quantile: float = LOWER_PROBABILITY_QUANTILE,
    kelly_multiplier: float = KELLY_MULTIPLIER,
    max_bankroll_fraction: float = MAX_BANKROLL_FRACTION,
) -> RoiKellyDecision:
    """One-sided Bayesian Kelly using only *settled* same-bookmaker evidence.

    historical_unit_pnl is sum of per-pick P&L divided by that pick's stake,
    i.e. +odds-1 on WIN and -1 on LOSS. All calculations are illustrative
    until evaluated point-in-time on fresh 1xBet quotes and walk-forward data.
    """
    if not bucket_id or not isinstance(bucket_id, str):
        raise ValueError("bucket_id must be a nonempty string")
    if (type(wins) is not int or type(losses) is not int or wins < 0 or losses < 0):
        raise ValueError("wins and losses must be nonnegative integers")
    n = wins + losses
    if type(bankroll_minor) is not int or bankroll_minor <= 0:
        raise ValueError("bankroll_minor must be a positive integer")
    if type(min_graded_n) is not int or min_graded_n < 1:
        raise ValueError("min_graded_n must be positive")
    if type(prior_equivalent_bets) is not int or prior_equivalent_bets <= 0:
        raise ValueError("prior_equivalent_bets must be positive")
    numeric = (historical_unit_pnl, quote_odds, lower_probability_quantile,
               kelly_multiplier, max_bankroll_fraction)
    if any(not isinstance(x, (int, float)) or not isfinite(float(x)) for x in numeric):
        raise ValueError("all numeric inputs must be finite")
    if quote_odds <= 1:
        raise ValueError("quote_odds must exceed 1")
    if not (0 < lower_probability_quantile < 0.5):
        raise ValueError("lower_probability_quantile must be between 0 and 0.5")
    if not (0 < kelly_multiplier <= 1 and 0 < max_bankroll_fraction <= 1):
        raise ValueError("Kelly multiplier and cap must be in (0, 1]")
    if historical_unit_pnl < -losses - 1e-6:
        raise ValueError("unit P&L cannot be lower than losing-stake total")
    historical_roi = (100 * historical_unit_pnl / n) if n else 0.0
    market_p = 1.0 / float(quote_odds)
    alpha = wins + 0.5 + prior_equivalent_bets * market_p
    beta_param = losses + 0.5 + prior_equivalent_bets * (1.0 - market_p)
    p_mean = alpha / (alpha + beta_param)
    p_low = float(beta.ppf(lower_probability_quantile, alpha, beta_param))
    conservative_roi_pct = 100 * (p_low * quote_odds - 1)
    raw_fraction = max(0.0, (p_low * quote_odds - 1) / (quote_odds - 1))

    reason = "PASS"
    if not verified_one_xbet:
        reason = "NOT_VERIFIED_1XBET"
    elif n < min_graded_n:
        reason = "INSUFFICIENT_SAME_BOOKMAKER_N"
    elif historical_roi <= 0:
        reason = "NON_POSITIVE_HISTORICAL_ROI"
    elif p_low <= market_p:
        reason = "NO_CONSERVATIVE_EDGE"

    applied = (
        min(raw_fraction * kelly_multiplier, max_bankroll_fraction)
        if reason == "PASS" else 0.0
    )
    stake = int(
        (Decimal(bankroll_minor) * Decimal(str(applied))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )
    if stake == 0 and reason == "PASS":
        reason = "STAKE_ROUNDS_TO_ZERO"
        applied = 0.0
    return RoiKellyDecision(
        bucket_id=bucket_id,
        graded_n=n,
        wins=wins,
        losses=losses,
        historical_roi_pct=historical_roi,
        quote_odds=float(quote_odds),
        break_even_probability=market_p,
        posterior_mean_probability=p_mean,
        conservative_probability=p_low,
        conservative_roi_pct=conservative_roi_pct,
        raw_kelly_fraction=raw_fraction,
        applied_fraction=applied,
        stake_minor=stake,
        decision="BET" if stake > 0 else "NO_BET",
        reason=reason,
    )
