"""Legacy registration helper and Task #10 durable registration use cases."""

from collections.abc import Callable
from datetime import UTC, datetime

from h2h.decisions.pick_eligibility import EligibilityDecision, EligibilityStatus
from h2h.domain.pick_decision import RegistrationResult
from h2h.domain.pick_registration import PickRegistration
from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.persistence.pick_registration import (
    BankrollBootstrapResult,
    PickRegistrationRepository,
)


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


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


class RegisterEligiblePick:
    """Register one persisted Task #9 evaluation through the atomic repository boundary."""

    def __init__(
        self,
        repository: PickRegistrationRepository,
        policy: RegistrationPolicyConfig,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._clock = clock

    def execute(self, evaluation_id: str, registration_request_id: str) -> RegistrationResult:
        return self._repository.register(
            evaluation_id,
            registration_request_id,
            self._policy,
            decided_at=_now(self._clock),
        )


class BootstrapBankroll:
    """Explicit, idempotent initialization of the configured bankroll account."""

    def __init__(
        self,
        repository: PickRegistrationRepository,
        policy: RegistrationPolicyConfig,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._clock = clock

    def execute(self) -> BankrollBootstrapResult:
        return self._repository.bootstrap_bankroll(self._policy, occurred_at=_now(self._clock))
