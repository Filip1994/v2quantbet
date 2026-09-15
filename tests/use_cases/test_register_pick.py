from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from h2h.decisions.pick_eligibility import EligibilityDecision, EligibilityStatus
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.pick_registration import PickRegistration, PickStatus
from h2h.domain.value_pick import evaluate_value
from h2h.use_cases.register_pick import RejectedPickRegistrationError, register_pick

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)


@pytest.fixture
def valuation():
    return evaluate_value(
        CanonicalQuote(
            "fixture-1", 8, "Bet365", Market.OU_25, Selection.OVER, 1.9, NOW, "test",
        ),
        0.70,
    )


def test_positive_ev_does_not_override_rejection(valuation):
    assert valuation.expected_value > 0
    decision = EligibilityDecision(
        "decision-1", valuation, EligibilityStatus.REJECTED, "TEST_POLICY_REJECTION",
    )
    with pytest.raises(RejectedPickRegistrationError, match="TEST_POLICY_REJECTION"):
        register_pick(decision, pick_id="pick-1", registered_at=NOW)


def test_plain_valuation_cannot_be_registered(valuation):
    with pytest.raises(TypeError, match="EligibilityDecision"):
        register_pick(valuation, pick_id="pick-1", registered_at=NOW)


def test_approved_decision_registers_exact_valuation_and_provenance(valuation):
    decision = EligibilityDecision("decision-1", valuation, EligibilityStatus.APPROVED)
    record = register_pick(decision, pick_id="pick-1", registered_at=NOW)
    assert record.value_pick is decision.value_pick
    assert record.eligibility_decision_id == decision.decision_id
    assert record.pick_id == "pick-1"
    assert record.fixture_id == valuation.quote.fixture_id
    assert record.registered_at == NOW
    assert record.status is PickStatus.REGISTERED
    with pytest.raises(FrozenInstanceError):
        record.eligibility_decision_id = "another-decision"
    with pytest.raises(FrozenInstanceError):
        record.value_pick = evaluate_value(valuation.quote, 0.50)


def test_caller_cannot_substitute_valuation(valuation):
    decision = EligibilityDecision("decision-1", valuation, EligibilityStatus.APPROVED)
    other = evaluate_value(valuation.quote, 0.50)
    with pytest.raises(TypeError, match="value_pick"):
        register_pick(decision, pick_id="pick-1", registered_at=NOW, value_pick=other)


def test_gate_does_not_introduce_an_ev_policy(valuation):
    # Synthetic approval exercises structure only, not a betting strategy.
    negative = evaluate_value(valuation.quote, 0.0)
    decision = EligibilityDecision("decision-1", negative, EligibilityStatus.APPROVED)
    assert register_pick(decision, pick_id="pick-1", registered_at=NOW).value_pick is negative


@pytest.mark.parametrize(
    ("pick_id", "registered_at", "error"),
    [
        ("", NOW, ValueError),
        (123, NOW, TypeError),
        ("pick-1", "not-a-date", TypeError),
        ("pick-1", NOW.replace(tzinfo=None), ValueError),
    ],
)
def test_existing_registration_validation_is_preserved(valuation, pick_id, registered_at, error):
    decision = EligibilityDecision("decision-1", valuation, EligibilityStatus.APPROVED)
    with pytest.raises(error):
        register_pick(decision, pick_id=pick_id, registered_at=registered_at)


def test_direct_domain_construction_remains_compatible(valuation):
    assert PickRegistration("pick-1", valuation, NOW).eligibility_decision_id is None


@pytest.mark.parametrize(("decision_id", "error"), [("", ValueError), (" ", ValueError), (1, TypeError)])
def test_supplied_provenance_requires_nonempty_string(valuation, decision_id, error):
    with pytest.raises(error, match="eligibility_decision_id"):
        PickRegistration("pick-1", valuation, NOW, eligibility_decision_id=decision_id)
