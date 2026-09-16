"""Explicit legacy and durable production eligibility decisions."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from h2h.domain.bookmaker_policy import API_FOOTBALL_BOOKMAKERS
from h2h.domain.fixture_record import FixtureObservation
from h2h.domain.pick_decision import EligibilityRejectionCode
from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.domain.value_evaluation import ValueEvaluation
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


def evaluate_persisted_eligibility(
    evaluation: ValueEvaluation,
    fixture: FixtureObservation,
    policy: RegistrationPolicyConfig,
    *,
    decided_at: datetime,
) -> tuple[EligibilityRejectionCode, ...]:
    """Return every applicable V1 rejection in stable enum order."""

    if evaluation.fixture_id != fixture.fixture_id:
        raise ValueError("evaluation and fixture observation provenance disagree")
    evaluation.validate_arithmetic()
    failures: set[EligibilityRejectionCode] = set()
    if (evaluation.market, evaluation.selected_selection) not in set(
        policy.allowed_market_selections
    ):
        failures.add(EligibilityRejectionCode.MARKET_SELECTION_NOT_ALLOWED)
    if API_FOOTBALL_BOOKMAKERS.get(evaluation.bookmaker_id) != evaluation.bookmaker_key:
        failures.add(EligibilityRejectionCode.BOOKMAKER_NOT_ALLOWED)
    if evaluation.devig_method_version not in policy.allowed_devig_methods:
        failures.add(EligibilityRejectionCode.DEVIG_METHOD_NOT_ALLOWED)
    if Decimal(str(evaluation.edge)) < policy.minimum_edge:
        failures.add(EligibilityRejectionCode.EDGE_BELOW_MINIMUM)
    if Decimal(str(evaluation.expected_value)) < policy.minimum_expected_value:
        failures.add(EligibilityRejectionCode.EXPECTED_VALUE_BELOW_MINIMUM)
    odds = Decimal(str(evaluation.selected_odd))
    if odds < policy.minimum_odds:
        failures.add(EligibilityRejectionCode.ODDS_BELOW_MINIMUM)
    if odds > policy.maximum_odds:
        failures.add(EligibilityRejectionCode.ODDS_ABOVE_MAXIMUM)
    if (
        evaluation.quote_observed_at > decided_at
        or evaluation.selected_captured_at > decided_at
        or evaluation.companion_captured_at > decided_at
    ):
        failures.add(EligibilityRejectionCode.QUOTE_NOT_YET_AVAILABLE)
    if evaluation.quote_observed_at <= decided_at and (
        decided_at - evaluation.quote_observed_at
    ).total_seconds() > (
        policy.maximum_quote_age_seconds
    ):
        failures.add(EligibilityRejectionCode.QUOTE_TOO_OLD)
    if evaluation.quote_observed_at >= fixture.kickoff_at:
        failures.add(EligibilityRejectionCode.QUOTE_NOT_PREMATCH)
    if decided_at >= fixture.kickoff_at:
        failures.add(EligibilityRejectionCode.REGISTRATION_NOT_PREMATCH)
    elif (fixture.kickoff_at - decided_at).total_seconds() < (
        policy.minimum_time_to_kickoff_seconds
    ):
        failures.add(EligibilityRejectionCode.REGISTRATION_TOO_CLOSE_TO_KICKOFF)
    if fixture.provider_status not in policy.allowed_fixture_statuses:
        failures.add(EligibilityRejectionCode.FIXTURE_STATUS_NOT_ALLOWED)
    return tuple(code for code in EligibilityRejectionCode if code in failures)
