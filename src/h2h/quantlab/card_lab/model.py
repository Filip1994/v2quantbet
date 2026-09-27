"""CardLab single-book structural probability model."""

from __future__ import annotations

from math import exp, floor, isfinite


MODEL_NAME = "Referee card-rate Poisson"
MODEL_VERSION = "CARDLAB_REFEREE_POISSON_V1"


def total_cards_probability(
    *,
    referee_card_rate: float,
    selection: str,
    line: float,
) -> float:
    """Return P(OVER/UNDER) for a half-line under a Poisson total-card model."""
    rate = float(referee_card_rate)
    target_line = float(line)
    if not isfinite(rate) or rate <= 0:
        raise ValueError("referee_card_rate must be positive and finite")
    if not isfinite(target_line) or target_line < 0:
        raise ValueError("line must be finite and non-negative")
    doubled = target_line * 2.0
    nearest = round(doubled)
    if abs(doubled - nearest) > 1e-9 or int(nearest) % 2 != 1:
        raise ValueError("CardLab Poisson model supports half-lines only")

    threshold = int(floor(target_line))
    term = exp(-rate)
    cdf = term
    for count in range(1, threshold + 1):
        term *= rate / count
        cdf += term
    cdf = min(1.0, max(0.0, cdf))

    side = str(selection).strip().upper()
    if side == "UNDER":
        probability = cdf
    elif side == "OVER":
        probability = 1.0 - cdf
    else:
        raise ValueError("selection must be OVER or UNDER")

    # Persistence requires an open probability interval.
    return min(1.0 - 1e-9, max(1e-9, probability))
