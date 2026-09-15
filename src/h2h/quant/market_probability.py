"""Select a model probability for canonical quote dimensions, without betting policy."""

from collections.abc import Mapping
from math import isfinite
from numbers import Real

from h2h.domain.odds import Market, Selection


def model_probability_for_selection(
    probabilities: Mapping[str, float],
    *,
    market: Market,
    selection: Selection,
) -> float:
    """Map one selection; callers must associate model output with the correct fixture.

    Only the consumed real scalar is validated. BTTS NO is the complement of
    validated BTTS YES under the model's normalized probability contract.
    """
    if not isinstance(probabilities, Mapping):
        raise TypeError("probabilities must be a Mapping")
    if not isinstance(market, Market):
        raise TypeError("market must be a Market")
    if not isinstance(selection, Selection):
        raise TypeError("selection must be a Selection")

    keys = {
        (Market.OU_25, Selection.OVER): "OVER_2_5",
        (Market.OU_25, Selection.UNDER): "UNDER_2_5",
        (Market.BTTS, Selection.YES): "BTTS_YES",
        (Market.BTTS, Selection.NO): "BTTS_YES",
    }
    try:
        key = keys[market, selection]
    except KeyError:
        raise ValueError(f"unsupported market/selection: {market.value}/{selection.value}") from None
    try:
        value = probabilities[key]
    except KeyError:
        raise ValueError(f"missing model probability: {key}") from None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{key} must be a real numeric scalar, not bool")
    if not 0.0 <= value <= 1.0 or not isfinite(value):
        raise ValueError(f"{key} must be finite and between 0 and 1")
    probability = float(value)
    return 1.0 - probability if selection is Selection.NO else probability
