"""Central bookmaker eligibility policy for QuantBet.

Only bookmakers explicitly approved for the Serbian operating scope may provide
odds or betting references. Keep normalization deterministic and side-effect free.
"""

from __future__ import annotations

from typing import Final


SUPPORTED_BOOKMAKERS: Final[frozenset[str]] = frozenset(
    {"superbet", "1xbet", "bet365"}
)


class UnsupportedBookmakerError(ValueError):
    """Raised when a bookmaker is outside the approved QuantBet allowlist."""


def normalize_bookmaker_id(bookmaker_id: str) -> str:
    """Normalize a bookmaker identifier for policy checks."""
    if not isinstance(bookmaker_id, str):
        raise TypeError("bookmaker_id must be a string")
    normalized = bookmaker_id.strip().casefold()
    if not normalized:
        raise ValueError("bookmaker_id must not be empty")
    return normalized


def is_supported_bookmaker(bookmaker_id: str) -> bool:
    """Return whether *bookmaker_id* belongs to the approved allowlist."""
    return normalize_bookmaker_id(bookmaker_id) in SUPPORTED_BOOKMAKERS


def require_supported_bookmaker(bookmaker_id: str) -> str:
    """Return the normalized ID or reject an ineligible bookmaker."""
    normalized = normalize_bookmaker_id(bookmaker_id)
    if normalized not in SUPPORTED_BOOKMAKERS:
        raise UnsupportedBookmakerError(
            f"unsupported bookmaker: {normalized!r}; "
            f"supported values: {sorted(SUPPORTED_BOOKMAKERS)!r}"
        )
    return normalized
