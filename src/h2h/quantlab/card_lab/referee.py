"""Stable matching for API-Football referee names across seasons."""

from __future__ import annotations


def referee_key(value: object) -> str:
    """Ignore the country suffix that older fixture seasons append after a comma."""
    return " ".join(str(value or "").split(",", 1)[0].split()).casefold()
