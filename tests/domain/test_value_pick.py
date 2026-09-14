from datetime import UTC, datetime

import pytest

from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.value_pick import evaluate_value


def make_quote(odd: float = 1.90) -> CanonicalQuote:
    return CanonicalQuote(
        fixture_id="fixture-1",
        bookmaker_id=10,
        bookmaker_name="Bookmaker",
        market=Market.OU_25,
        selection=Selection.OVER,
        odd=odd,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        source="test",
    )


def test_evaluate_value_matches_probability_gap_and_ev_example() -> None:
    result = evaluate_value(make_quote(1.90), 0.70)

    assert result.quote == make_quote(1.90)
    assert result.model_probability == pytest.approx(0.70)
    assert result.implied_probability == pytest.approx(1 / 1.90)
    assert result.probability_gap == pytest.approx(0.70 - 1 / 1.90)
    assert result.expected_value == pytest.approx(0.33)


def test_model_probability_accepts_closed_interval_boundaries() -> None:
    zero = evaluate_value(make_quote(), 0.0)
    one = evaluate_value(make_quote(), 1.0)

    assert zero.model_probability == 0.0
    assert one.model_probability == 1.0


def test_model_probability_must_be_finite_and_between_zero_and_one() -> None:
    for invalid_probability in (-0.01, 1.01, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            evaluate_value(make_quote(), invalid_probability)
