from datetime import UTC, datetime
from fractions import Fraction
from types import MappingProxyType

import numpy as np
import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.value_pick import evaluate_value
from h2h.quant.dixon_coles import DixonColesModel
from h2h.quant.market_probability import model_probability_for_selection


CASES = [
    (Market.OU_25, Selection.OVER, "OVER_2_5", 0.23),
    (Market.OU_25, Selection.UNDER, "UNDER_2_5", 0.77),
    (Market.BTTS, Selection.YES, "BTTS_YES", 0.41),
    (Market.BTTS, Selection.NO, "BTTS_YES", 1.0 - 0.41),
]


@pytest.mark.parametrize("market,selection,key,expected", CASES)
def test_exact_mapping_and_input_is_unchanged(market, selection, key, expected):
    values = {"OVER_2_5": 0.23, "UNDER_2_5": 0.77, "BTTS_YES": 0.41}
    original = values.copy()
    result = model_probability_for_selection(MappingProxyType(values), market=market, selection=selection)
    assert result == expected
    assert type(result) is float
    assert values == original


@pytest.mark.parametrize("yes,expected", [(0, 1.0), (1, 0.0), (0.41, 1.0 - 0.41)])
def test_btts_no_complement(yes, expected):
    assert model_probability_for_selection(
        {"BTTS_YES": yes}, market=Market.BTTS, selection=Selection.NO,
    ) == expected


@pytest.mark.parametrize("market,selection,key,expected", CASES)
def test_only_consumed_key_is_required_and_validated(market, selection, key, expected):
    consumed = 0.41 if market is Market.BTTS else expected
    values = {key: consumed}
    assert model_probability_for_selection(values, market=market, selection=selection) == expected
    values.update({other: object() for other in ("OVER_2_5", "UNDER_2_5", "BTTS_YES", "BTTS_NO") if other != key})
    assert model_probability_for_selection(values, market=market, selection=selection) == expected


@pytest.mark.parametrize("market,selection,key,expected", CASES)
def test_missing_key_never_falls_back(market, selection, key, expected):
    values = {other: 0.5 for other in ("OVER_2_5", "UNDER_2_5", "BTTS_YES", "BTTS_NO") if other != key}
    with pytest.raises(ValueError, match=key):
        model_probability_for_selection(values, market=market, selection=selection)


@pytest.mark.parametrize("market,selection", [
    (Market.OU_25, Selection.YES), (Market.OU_25, Selection.NO),
    (Market.BTTS, Selection.OVER), (Market.BTTS, Selection.UNDER),
])
def test_invalid_canonical_pair(market, selection):
    with pytest.raises(ValueError, match="unsupported market/selection"):
        model_probability_for_selection({}, market=market, selection=selection)


@pytest.mark.parametrize("field,value", [
    ("market", "OU_25"), ("market", "unknown"), ("market", None),
    ("selection", "OVER"), ("selection", "unknown"), ("selection", 1),
    ("market", Selection.OVER), ("selection", Market.OU_25),
])
def test_noncanonical_dimensions(field, value):
    dimensions = {"market": Market.OU_25, "selection": Selection.OVER, field: value}
    with pytest.raises(TypeError, match=field):
        model_probability_for_selection({}, **dimensions)


@pytest.mark.parametrize("values", [None, [], [("BTTS_YES", 0.5)], "probabilities", 1])
def test_non_mapping(values):
    with pytest.raises(TypeError, match="Mapping"):
        model_probability_for_selection(values, market=Market.BTTS, selection=Selection.YES)


@pytest.mark.parametrize("selection", [Selection.YES, Selection.NO])
@pytest.mark.parametrize("value", [True, False, "0.5", None, [], {}, 0.5j, np.array([0.5])])
def test_malformed_consumed_scalar(value, selection):
    with pytest.raises(TypeError):
        model_probability_for_selection({"BTTS_YES": value}, market=Market.BTTS, selection=selection)


@pytest.mark.parametrize("selection", [Selection.YES, Selection.NO])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -0.01, 1.01, -1e-15, 1 + 1e-15])
def test_invalid_probability_is_rejected_not_clipped(value, selection):
    with pytest.raises(ValueError):
        model_probability_for_selection({"BTTS_YES": value}, market=Market.BTTS, selection=selection)


@pytest.mark.parametrize("value", [0, 1, 0.123456789012345, np.float64(0.37), Fraction(1, 4)])
def test_real_scalar_returns_float_without_rounding_or_renormalization(value):
    result = model_probability_for_selection(
        {"OVER_2_5": value, "UNDER_2_5": 0.99}, market=Market.OU_25, selection=Selection.OVER,
    )
    assert result == float(value)
    assert type(result) is float


@pytest.fixture
def matrix_model(monkeypatch):
    # Rows: home goals; columns: away goals. Total mass is one.
    matrix = np.array([[0.05, 0.10, 0.15], [0.20, 0.10, 0.05], [0.10, 0.15, 0.10]])
    model = DixonColesModel((1, 2), np.zeros(2), np.zeros(2), 0.0, 0.0, 0.0, 0.0, 0, 0.0)

    def score_matrix(self, home_id, away_id, max_goals=10):
        assert self is model
        assert (home_id, away_id) == (1, 2)
        return matrix.copy()

    monkeypatch.setattr(DixonColesModel, "score_matrix", score_matrix)
    return model


def test_producer_formulas_on_independent_normalized_matrix(matrix_model):
    probabilities = matrix_model.market_probabilities(1, 2)
    assert set(probabilities) == {"OVER_2_5", "UNDER_2_5", "BTTS_YES"}
    assert probabilities["UNDER_2_5"] == pytest.approx(0.70)
    assert probabilities["OVER_2_5"] == pytest.approx(0.30)
    assert probabilities["BTTS_YES"] == pytest.approx(0.40)
    no = model_probability_for_selection(probabilities, market=Market.BTTS, selection=Selection.NO)
    # Zero-home row plus zero-away column, counting 0-0 only once.
    assert no == pytest.approx(0.05 + 0.10 + 0.15 + 0.20 + 0.10)


@pytest.mark.parametrize("market,selection,expected", [
    (Market.OU_25, Selection.OVER, 0.30), (Market.OU_25, Selection.UNDER, 0.70),
    (Market.BTTS, Selection.YES, 0.40), (Market.BTTS, Selection.NO, 0.60),
])
def test_model_probabilities_bridge_to_valuation(matrix_model, market, selection, expected):
    quote = CanonicalQuote("fixture", 8, "Bookmaker", market, selection, 1.9, datetime(2026, 1, 1, tzinfo=UTC), "test")
    probabilities = matrix_model.market_probabilities(1, 2)
    probability = model_probability_for_selection(probabilities, market=quote.market, selection=quote.selection)
    result = evaluate_value(quote, probability)
    assert result.quote is quote
    assert result.model_probability == probability
    assert result.model_probability == pytest.approx(expected)
