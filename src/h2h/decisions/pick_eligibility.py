"""Explicit eligibility results; acceptance policy is supplied by future callers."""

import re
from dataclasses import dataclass
from enum import StrEnum

from h2h.domain.value_pick import ValuePick


class EligibilityStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """A caller-identified decision about exactly one immutable valuation.

    Rejection codes are stable uppercase tokens, not display messages. Their
    vocabulary belongs to the future acceptance policy; this model runs no rules.
    """

    decision_id: str
    value_pick: ValuePick
    status: EligibilityStatus
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision_id, str):
            raise TypeError("decision_id must be a string")
        if not self.decision_id.strip():
            raise ValueError("decision_id must not be empty")
        if not isinstance(self.value_pick, ValuePick):
            raise TypeError("value_pick must be a ValuePick")
        if not isinstance(self.status, EligibilityStatus):
            raise TypeError("status must be an EligibilityStatus")
        if self.status is EligibilityStatus.APPROVED:
            if self.rejection_reason is not None:
                raise ValueError("approved decision must not have a rejection reason")
        elif (
            not isinstance(self.rejection_reason, str)
            or re.fullmatch(r"[A-Z][A-Z0-9_]*", self.rejection_reason) is None
        ):
            raise ValueError("rejected decision requires a reason code matching [A-Z][A-Z0-9_]*")
