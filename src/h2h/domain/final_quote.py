"""Durable state for mandatory pre-acceptance quote verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class FinalQuoteStatus(StrEnum):
    REQUESTED = "REQUESTED"
    READY = "READY"
    REJECTED = "REJECTED"


class FinalQuoteRejectionCode(StrEnum):
    FINAL_QUOTE_REFRESH_BUDGET_UNAVAILABLE = "FINAL_QUOTE_REFRESH_BUDGET_UNAVAILABLE"
    FINAL_QUOTE_REFRESH_PROVIDER_ERROR = "FINAL_QUOTE_REFRESH_PROVIDER_ERROR"
    FINAL_QUOTE_MARKET_INCOMPLETE = "FINAL_QUOTE_MARKET_INCOMPLETE"
    FINAL_QUOTE_MARKET_MISMATCH = "FINAL_QUOTE_MARKET_MISMATCH"
    FINAL_QUOTE_STALE = "FINAL_QUOTE_STALE"
    FINAL_QUOTE_LIVE_PROXY_BELOW_MINIMUM = "FINAL_QUOTE_LIVE_PROXY_BELOW_MINIMUM"
    FINAL_QUOTE_REFRESH_REQUIRED = "FINAL_QUOTE_REFRESH_REQUIRED"
    MODEL_INACTIVE_OR_STALE = "MODEL_INACTIVE_OR_STALE"


@dataclass(frozen=True, slots=True)
class FinalQuoteClaim:
    verification_id: str
    preliminary_evaluation_id: str
    status: FinalQuoteStatus
    should_fetch: bool
    final_evaluation_id: str | None = None
    reason_codes: tuple[str, ...] = ()


def utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)
