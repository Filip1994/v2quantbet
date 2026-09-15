"""Stateful kickoff-aware scheduling for selective quote refreshes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from h2h.workers.quote_refresh_schedule import quote_refresh_decision


@dataclass(frozen=True, slots=True)
class ScheduledRefresh:
    """Current scheduling state for one provider fixture."""

    fixture_id: int
    kickoff_at: datetime
    next_refresh_at: datetime
    closing_capture_required: bool = False


class QuoteRefreshScheduler:
    """Track when each fixture becomes due for its next quote refresh."""

    def __init__(self) -> None:
        self._state: dict[int, ScheduledRefresh] = {}

    def register(
        self,
        *,
        fixture_id: int,
        kickoff_at: datetime,
        now: datetime,
    ) -> ScheduledRefresh | None:
        """Register or replace one fixture and calculate its first refresh due time."""
        decision = quote_refresh_decision(now=now, kickoff_at=kickoff_at)
        if not decision.eligible or decision.interval is None:
            self._state.pop(fixture_id, None)
            return None
        scheduled = ScheduledRefresh(
            fixture_id=fixture_id,
            kickoff_at=kickoff_at,
            next_refresh_at=now + decision.interval,
            closing_capture_required=decision.closing_capture,
        )
        self._state[fixture_id] = scheduled
        return scheduled

    def due_fixture_ids(self, *, now: datetime) -> tuple[int, ...]:
        """Return fixtures due for refresh at or before the supplied instant."""
        due = []
        for fixture_id, state in self._state.items():
            decision = quote_refresh_decision(now=now, kickoff_at=state.kickoff_at)
            if not decision.eligible:
                continue
            if state.next_refresh_at <= now:
                due.append(fixture_id)
        return tuple(sorted(due))

    def mark_refreshed(self, *, fixture_id: int, now: datetime) -> ScheduledRefresh | None:
        """Advance one fixture to its next cadence after a successful refresh."""
        state = self._state.get(fixture_id)
        if state is None:
            return None
        decision = quote_refresh_decision(now=now, kickoff_at=state.kickoff_at)
        if not decision.eligible or decision.interval is None:
            self._state.pop(fixture_id, None)
            return None
        updated = ScheduledRefresh(
            fixture_id=fixture_id,
            kickoff_at=state.kickoff_at,
            next_refresh_at=now + decision.interval,
            closing_capture_required=decision.closing_capture,
        )
        self._state[fixture_id] = updated
        return updated

    def remove(self, *, fixture_id: int) -> None:
        """Remove one fixture from the active schedule."""
        self._state.pop(fixture_id, None)

    def snapshot(self) -> tuple[ScheduledRefresh, ...]:
        """Return all active schedule entries in deterministic fixture order."""
        return tuple(self._state[fixture_id] for fixture_id in sorted(self._state))
