"""Versioned ownership classification for raw API-Football markets."""

from __future__ import annotations

import re
from dataclasses import dataclass


CLASSIFIER_VERSION = "MARKET_CLASSIFIER_V1"
LAB_OWNERS = frozenset({"GOAL", "CORNER", "CARD", "UNCLASSIFIED"})


def _tokens(value: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


@dataclass(frozen=True, slots=True)
class MarketClassification:
    owner: str
    version: str = CLASSIFIER_VERSION

    def __post_init__(self) -> None:
        if self.owner not in LAB_OWNERS:
            raise ValueError("unsupported QuantLab market owner")


def classify_market(provider_bet_id: int, provider_bet_name: str) -> MarketClassification:
    """Classify ownership only; never infer settlement semantics."""
    if isinstance(provider_bet_id, bool) or not isinstance(provider_bet_id, int) or provider_bet_id <= 0:
        raise ValueError("provider_bet_id must be a positive integer")
    if not isinstance(provider_bet_name, str) or not provider_bet_name.strip():
        raise ValueError("provider_bet_name must be non-empty")

    tokens = _tokens(provider_bet_name)
    if {"corner", "corners"} & tokens:
        return MarketClassification("CORNER")
    if {"card", "cards", "booking", "bookings", "yellow", "red", "foul", "fouls"} & tokens:
        return MarketClassification("CARD")
    if (
        {"goal", "goals", "score", "scoring", "btts"} & tokens
        or {"both", "teams", "score"} <= tokens
        or {"clean", "sheet"} <= tokens
    ):
        return MarketClassification("GOAL")
    return MarketClassification("UNCLASSIFIED")
