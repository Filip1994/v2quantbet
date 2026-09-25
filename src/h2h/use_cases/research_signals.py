"""Use cases for durable exposure-blocked research signals."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


class RecordExposureBlockedResearchSignal:
    """Persist a qualifying signal that was blocked only by open exposure."""

    def __init__(
        self,
        repository: PostgreSQLResearchSignalRepository,
        policy: RegistrationPolicyConfig,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(policy, RegistrationPolicyConfig):
            raise TypeError("policy must be a RegistrationPolicyConfig")
        self._repository = repository
        self._policy = policy
        self._clock = clock

    def execute(self, evaluation_id: str) -> str:
        return self._repository.record_exposure_blocked(
            evaluation_id,
            self._policy,
            detected_at=_now(self._clock),
        )
