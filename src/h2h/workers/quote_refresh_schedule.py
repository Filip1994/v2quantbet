"""Kickoff-aware quote refresh policy for pre-match quote collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class QuoteRefreshDecision:
    """Refresh policy decision for one fixture at a given instant."""

    eligible: bool
    interval: timedelta | None
    closing_capture: bool = False
    reason: str = ""


# The policy is intentionally conservative. Boundary points belong to the
# tighter (more frequent) window, except the 72-hour upper boundary which is
# included in the first window.

def quote_refresh_decision(
    *,
    now: datetime,
    kickoff_at: datetime,
) -> QuoteRefreshDecision:
    """Return the refresh cadence applicable to a scheduled fixture.

    Naive datetimes are rejected because comparing timestamps from different
    time bases would make refresh decisions unsafe. Fixtures after kickoff or
    more than 72 hours away are not eligible for this pre-match policy.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if kickoff_at.tzinfo is None or kickoff_at.utcoffset() is None:
        raise ValueError("kickoff_at must be timezone-aware")

    time_to_kickoff = kickoff_at - now
    if time_to_kickoff <= timedelta(0):
        return QuoteRefreshDecision(False, None, reason="fixture already started")
    if time_to_kickoff > timedelta(hours=72):
        return QuoteRefreshDecision(False, None, reason="fixture is outside 72-hour window")

    if time_to_kickoff <= timedelta(minutes=15):
        return QuoteRefreshDecision(
            True,
            timedelta(minutes=30),
            closing_capture=True,
            reason="final 15-minute window",
        )
    if time_to_kickoff <= timedelta(hours=2):
        return QuoteRefreshDecision(True, timedelta(minutes=30), reason="T-2h to kickoff")
    if time_to_kickoff <= timedelta(hours=6):
        return QuoteRefreshDecision(True, timedelta(hours=2), reason="T-6h to T-2h")
    if time_to_kickoff <= timedelta(hours=24):
        return QuoteRefreshDecision(True, timedelta(hours=6), reason="T-24h to T-6h")
    if time_to_kickoff <= timedelta(hours=48):
        return QuoteRefreshDecision(True, timedelta(hours=12), reason="T-48h to T-24h")
    return QuoteRefreshDecision(True, timedelta(hours=24), reason="T-72h to T-48h")
