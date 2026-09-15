"""Register a valuation only after an explicit approved eligibility decision."""

from datetime import datetime

from h2h.decisions.pick_eligibility import EligibilityDecision, EligibilityStatus
from h2h.domain.pick_registration import PickRegistration


class RejectedPickRegistrationError(ValueError):
    """A rejected eligibility decision cannot produce a registration."""


def register_pick(
    decision: EligibilityDecision,
    *,
    pick_id: str,
    registered_at: datetime,
) -> PickRegistration:
    """Keep the decision's exact valuation and delegate ID/time checks to the record."""
    if not isinstance(decision, EligibilityDecision):
        raise TypeError("decision must be an EligibilityDecision")
    if decision.status is EligibilityStatus.REJECTED:
        raise RejectedPickRegistrationError(
            f"cannot register rejected decision {decision.decision_id!r}: "
            f"{decision.rejection_reason}"
        )
    return PickRegistration(
        pick_id=pick_id,
        value_pick=decision.value_pick,
        registered_at=registered_at,
        eligibility_decision_id=decision.decision_id,
    )
