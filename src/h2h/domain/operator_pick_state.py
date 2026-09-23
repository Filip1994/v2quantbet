"""Minimal operator PLAYED/SKIPPED state with PLAYED as the derived default."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class OperatorPickState(StrEnum):
    PLAYED = "PLAYED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True, slots=True)
class OperatorPickStateEvent:
    event_id: str
    pick_id: str
    state: OperatorPickState
    occurred_at: datetime
    request_id: str

    def __post_init__(self) -> None:
        for name in ("event_id", "pick_id", "request_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.state, OperatorPickState):
            raise TypeError("state must be an OperatorPickState")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))
