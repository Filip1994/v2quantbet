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


@dataclass(frozen=True, slots=True)
class StaleQuoteRetryPolicy:
    """Operational retry bounds for stale provider observations."""

    initial_interval: timedelta
    max_interval: timedelta
    max_attempts: int
    horizon: timedelta

    def __post_init__(self) -> None:
        if self.initial_interval <= timedelta(0):
            raise ValueError("stale quote initial interval must be positive")
        if self.max_interval < self.initial_interval:
            raise ValueError("stale quote max interval must be at least the initial interval")
        if self.max_attempts <= 0:
            raise ValueError("stale quote max attempts must be positive")
        if self.horizon < self.initial_interval:
            raise ValueError("stale quote retry horizon must be at least the initial interval")

    def next_retry_at(
        self,
        *,
        stale_attempt_count: int,
        first_stale_at: datetime,
        attempted_at: datetime,
    ) -> datetime | None:
        """Return the next bounded retry after a stale response.

        ``stale_attempt_count`` includes the initial normal-cadence pull that
        first discovered stale provider data.  The configured attempt bound
        therefore also bounds the number of stale responses that can keep the
        accelerated path active.
        """
        if stale_attempt_count <= 0:
            raise ValueError("stale_attempt_count must be positive")
        for value, name in (
            (first_stale_at, "first_stale_at"),
            (attempted_at, "attempted_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if stale_attempt_count >= self.max_attempts:
            return None
        interval = min(
            self.initial_interval * (2 ** (stale_attempt_count - 1)),
            self.max_interval,
        )
        candidate = attempted_at + interval
        deadline = first_stale_at + self.horizon
        return candidate if candidate <= deadline else None


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
