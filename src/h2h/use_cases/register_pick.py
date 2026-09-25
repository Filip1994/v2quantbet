"""Legacy registration helper and Task #10 durable registration use cases."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from h2h.decisions.pick_eligibility import EligibilityDecision, EligibilityStatus
from h2h.domain.final_quote import FinalQuoteClaim
from h2h.domain.pick_decision import RegistrationResult
from h2h.domain.pick_registration import PickRegistration
from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.persistence.pick_registration import (
    BankrollBootstrapResult,
    PickRegistrationRepository,
    RegistrationProvenanceError,
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
        require_final_quote_verification: bool = False,
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._clock = clock
        self._require_final_quote_verification = require_final_quote_verification

    def execute(
        self,
        evaluation_id: str,
        registration_request_id: str,
        *,
        final_quote_verification_id: str | None = None,
    ) -> RegistrationResult:
        if self._require_final_quote_verification and final_quote_verification_id is None:
            raise RegistrationProvenanceError(
                "production registration requires final quote verification"
            )
        arguments = {"decided_at": _now(self._clock)}
        if final_quote_verification_id is not None:
            arguments["final_quote_verification_id"] = final_quote_verification_id
        return self._repository.register(
            evaluation_id, registration_request_id, self._policy, **arguments
        )

    def preliminary_rejection_codes(self, evaluation_id: str) -> tuple[str, ...]:
        return self._repository.preliminary_rejection_codes(
            evaluation_id, self._policy, checked_at=_now(self._clock)
        )

    def record_exposure_blocked_signal(
        self,
        evaluation_id: str,
        *,
        capture_origin: str = "LIVE",
    ) -> None:
        self._repository.record_exposure_blocked_signal(
            evaluation_id,
            self._policy,
            blocked_at=_now(self._clock),
            capture_origin=capture_origin,
        )

    def minimum_playable_odds(self, model_probability: float) -> float:
        probability = Decimal(str(model_probability))
        if not Decimal(0) < probability <= Decimal(1):
            raise ValueError("model_probability must be in (0, 1]")
        return float((Decimal(1) + self._policy.minimum_expected_value) / probability)

    def begin_final_quote_verification(self, evaluation_id: str) -> FinalQuoteClaim:
        return self._repository.begin_final_quote_verification(
            evaluation_id, requested_at=_now(self._clock)
        )

    def reject_final_quote_verification(
        self,
        verification_id: str,
        *,
        reason_codes: tuple[str, ...],
        budget_outcome: str = "ALLOWED",
        returned_source: str | None = None,
        returned_observed_at: datetime | None = None,
        returned_captured_at: datetime | None = None,
        quote_age_seconds: float | None = None,
    ) -> FinalQuoteClaim:
        return self._repository.reject_final_quote_verification(
            verification_id,
            reason_codes=reason_codes,
            budget_outcome=budget_outcome,
            returned_source=returned_source,
            returned_observed_at=returned_observed_at,
            returned_captured_at=returned_captured_at,
            quote_age_seconds=quote_age_seconds,
            decided_at=_now(self._clock),
        )

    def complete_final_quote_verification(
        self,
        verification_id: str,
        final_evaluation_id: str,
        *,
        captured_at: datetime,
        quote_age_seconds: float,
        snapshot_ids: tuple[str, str],
        stale_quote: bool,
        model_probability: float,
    ) -> FinalQuoteClaim:
        return self._repository.complete_final_quote_verification(
            verification_id,
            final_evaluation_id,
            captured_at=captured_at,
            quote_age_seconds=quote_age_seconds,
            snapshot_ids=snapshot_ids,
            stale_quote=stale_quote,
            minimum_playable_odds=self.minimum_playable_odds(model_probability),
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
