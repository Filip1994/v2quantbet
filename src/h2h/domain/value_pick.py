"""Deterministic comparison between model probability and bookmaker price."""

from dataclasses import dataclass
from math import isfinite

from h2h.domain.odds import CanonicalQuote


@dataclass(frozen=True, slots=True)
class ValuePick:
    """A model-vs-market valuation for one canonical quote."""

    quote: CanonicalQuote
    model_probability: float
    implied_probability: float
    probability_gap: float
    expected_value: float


def evaluate_value(quote: CanonicalQuote, model_probability: float) -> ValuePick:
    """Evaluate a quote using decimal odds and a model probability.

    ``probability_gap`` is measured in probability points as a decimal
    (0.1737 means +17.37 percentage points). ``expected_value`` is the
    net expected return per unit stake.
    """
    if not isfinite(model_probability) or not 0.0 <= model_probability <= 1.0:
        raise ValueError("model_probability must be finite and between 0 and 1")

    implied_probability = 1.0 / quote.odd
    probability_gap = model_probability - implied_probability
    expected_value = model_probability * quote.odd - 1.0
    return ValuePick(
        quote=quote,
        model_probability=model_probability,
        implied_probability=implied_probability,
        probability_gap=probability_gap,
        expected_value=expected_value,
    )
