from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from h2h.decisions.pick_eligibility import EligibilityDecision, EligibilityStatus
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.value_pick import evaluate_value


@pytest.fixture
def valuation():
    return evaluate_value(
        CanonicalQuote(
            "fixture-1", 8, "Bet365", Market.OU_25, Selection.OVER, 1.9,
            datetime(2026, 9, 15, tzinfo=UTC), "test",
        ),
        0.70,
    )


def test_decision_binds_exact_valuation_and_is_immutable(valuation):
    decision = EligibilityDecision("decision-1", valuation, EligibilityStatus.APPROVED)
    assert decision.value_pick is valuation
    with pytest.raises(FrozenInstanceError):
        decision.status = EligibilityStatus.REJECTED
    with pytest.raises(FrozenInstanceError):
        decision.value_pick = evaluate_value(valuation.quote, 0.50)


def test_rejection_preserves_caller_defined_code(valuation):
    decision = EligibilityDecision(
        "decision-1", valuation, EligibilityStatus.REJECTED, "TEST_POLICY_REJECTION",
    )
    assert decision.rejection_reason == "TEST_POLICY_REJECTION"
    assert decision.value_pick is valuation


@pytest.mark.parametrize("reason", [None, "", " ", "display message", "lowercase", 123])
def test_rejection_requires_machine_readable_code(valuation, reason):
    with pytest.raises(ValueError, match="reason code"):
        EligibilityDecision("decision-1", valuation, EligibilityStatus.REJECTED, reason)


@pytest.mark.parametrize("reason", ["TEST_POLICY_REJECTION", ""])
def test_approval_cannot_carry_rejection_reason(valuation, reason):
    with pytest.raises(ValueError, match="must not have"):
        EligibilityDecision("decision-1", valuation, EligibilityStatus.APPROVED, reason)


@pytest.mark.parametrize("status", [True, "approved", "rejected", None])
def test_status_requires_explicit_enum(valuation, status):
    with pytest.raises(TypeError, match="EligibilityStatus"):
        EligibilityDecision("decision-1", valuation, status)


@pytest.mark.parametrize("decision_id", ["", " "])
def test_decision_id_is_required(valuation, decision_id):
    with pytest.raises(ValueError, match="decision_id"):
        EligibilityDecision(decision_id, valuation, EligibilityStatus.APPROVED)


def test_decision_requires_typed_id_and_valuation(valuation):
    with pytest.raises(TypeError, match="decision_id"):
        EligibilityDecision(123, valuation, EligibilityStatus.APPROVED)
    with pytest.raises(TypeError, match="ValuePick"):
        EligibilityDecision("decision-1", object(), EligibilityStatus.APPROVED)
