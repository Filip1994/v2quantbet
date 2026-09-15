"""Immutable registration record for a published value pick."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from h2h.domain.value_pick import ValuePick


class PickStatus(StrEnum):
    """Lifecycle states for a registered pick."""

    REGISTERED = "registered"
    VOIDED = "voided"
    SETTLED = "settled"


@dataclass(frozen=True, slots=True)
class PickRegistration:
    """Stable, immutable record of the exact value pick that was registered."""

    pick_id: str
    value_pick: ValuePick
    registered_at: datetime
    status: PickStatus = PickStatus.REGISTERED

    def __post_init__(self) -> None:
        if not isinstance(self.pick_id, str):
            raise TypeError("pick_id must be a string")
        if not self.pick_id.strip():
            raise ValueError("pick_id must not be empty")
        if not isinstance(self.registered_at, datetime):
            raise TypeError("registered_at must be a datetime")
        if self.registered_at.tzinfo is None or self.registered_at.utcoffset() is None:
            raise ValueError("registered_at must be timezone-aware")
        if not isinstance(self.status, PickStatus):
            raise TypeError("status must be a PickStatus")

    @property
    def fixture_id(self) -> str:
        """Return the fixture identity captured by the registered pick."""
        return self.value_pick.quote.fixture_id
