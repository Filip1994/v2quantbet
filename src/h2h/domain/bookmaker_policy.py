"""Central bookmaker eligibility policy for QuantBet.

Only bookmakers explicitly approved for the Serbian operating scope may provide
odds or betting references. Keep normalization deterministic and side-effect free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


SUPPORTED_BOOKMAKERS: Final[frozenset[str]] = frozenset(
    {"superbet", "1xbet", "bet365"}
)

# API-Football bookmaker IDs confirmed from the legacy H2H integration.
API_FOOTBALL_BOOKMAKERS: Final[dict[int, str]] = {
    8: "bet365",
    11: "1xbet",
    34: "superbet",
}

_EXPECTED_PROVIDER_NAMES: Final[dict[int, str]] = {
    8: "bet365",
    11: "1xbet",
    34: "superbet",
}


class UnsupportedBookmakerError(ValueError):
    """Raised when a bookmaker is outside the approved QuantBet allowlist."""


@dataclass(frozen=True, slots=True)
class BookmakerIdentity:
    """Validated provider identity while preserving provider-level provenance."""

    provider_id: int
    canonical_id: str
    provider_name: str


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


def resolve_api_football_bookmaker(
    provider_id: int, provider_name: str
) -> BookmakerIdentity:
    """Validate and resolve an API-Football bookmaker identity.

    Unknown provider IDs and contradictory provider names are rejected before a
    quote can enter the canonical domain model.
    """
    if isinstance(provider_id, bool) or not isinstance(provider_id, int):
        raise TypeError("provider_id must be an integer")
    if not isinstance(provider_name, str) or not provider_name.strip():
        raise ValueError("provider_name must not be empty")

    try:
        canonical_id = API_FOOTBALL_BOOKMAKERS[provider_id]
    except KeyError as exc:
        raise UnsupportedBookmakerError(
            f"unsupported API-Football bookmaker id: {provider_id}"
        ) from exc

    normalized_name = normalize_bookmaker_id(provider_name)
    expected_name = _EXPECTED_PROVIDER_NAMES[provider_id]
    if normalized_name != expected_name:
        raise UnsupportedBookmakerError(
            f"API-Football bookmaker id/name mismatch: {provider_id} / "
            f"{provider_name!r}"
        )

    return BookmakerIdentity(
        provider_id=provider_id,
        canonical_id=canonical_id,
        provider_name=provider_name.strip(),
    )
