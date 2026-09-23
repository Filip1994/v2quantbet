"""Persistence boundary and operational errors for Task #10 registration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from h2h.domain.pick_decision import RegistrationResult
from h2h.domain.final_quote import FinalQuoteClaim
from h2h.domain.registration_policy import RegistrationPolicyConfig


class RegistrationPersistenceConflictError(ValueError):
    """An immutable registration identity was reused inconsistently."""


class RegistrationProvenanceError(RuntimeError):
    """Required Task #9 durable provenance is missing or contradictory."""


class BankrollBootstrapConflictError(ValueError):
    """The bankroll was already bootstrapped with different immutable facts."""


class BankrollNotBootstrappedError(RuntimeError):
    """Registration cannot reserve funds before explicit bankroll bootstrap."""


@dataclass(frozen=True, slots=True)
class BankrollBootstrapResult:
    bankroll_account_id: str
    ledger_entry_id: str
    balance_minor: int
    currency: str


class PickRegistrationRepository(Protocol):
    def bootstrap_bankroll(
        self, policy: RegistrationPolicyConfig, *, occurred_at: datetime
    ) -> BankrollBootstrapResult: ...

    def register(
        self,
        evaluation_id: str,
        registration_request_id: str,
        policy: RegistrationPolicyConfig,
        *,
        decided_at: datetime,
        final_quote_verification_id: str | None = None,
    ) -> RegistrationResult: ...

    def preliminary_rejection_codes(
        self, evaluation_id: str, policy: RegistrationPolicyConfig, *, checked_at: datetime
    ) -> tuple[str, ...]: ...

    def begin_final_quote_verification(
        self, preliminary_evaluation_id: str, *, requested_at: datetime
    ) -> FinalQuoteClaim: ...
