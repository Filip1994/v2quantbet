"""Deterministic CardLab rivalry registry.

V1 is intentionally positive-only. A pair not present in the registry is UNKNOWN,
not automatically false. Explicit non-rivalry entries can be added separately.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


RIVALRY_REGISTRY_VERSION = "RIVALRY_REGISTRY_V1"


def _name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((_name(a), _name(b))))  # type: ignore[return-value]


_POSITIVE_PAIRS = frozenset(
    {
        _pair("Arsenal", "Tottenham"),
        _pair("Liverpool", "Everton"),
        _pair("Manchester United", "Manchester City"),
        _pair("Real Madrid", "Barcelona"),
        _pair("Real Madrid", "Atletico Madrid"),
        _pair("Sevilla", "Real Betis"),
        _pair("Inter", "AC Milan"),
        _pair("Roma", "Lazio"),
        _pair("Juventus", "Torino"),
        _pair("Borussia Dortmund", "Schalke 04"),
        _pair("Paris Saint Germain", "Marseille"),
        _pair("Ajax", "Feyenoord"),
        _pair("Benfica", "Sporting CP"),
        _pair("Celtic", "Rangers"),
        _pair("Galatasaray", "Fenerbahce"),
        _pair("Olympiakos Piraeus", "Panathinaikos"),
        _pair("Red Star Belgrade", "FK Partizan"),
        _pair("Dinamo Zagreb", "HNK Hajduk Split"),
        _pair("Boca Juniors", "River Plate"),
        _pair("Flamengo", "Fluminense"),
        _pair("Corinthians", "Palmeiras"),
        _pair("Gremio", "Internacional"),
        _pair("Los Angeles FC", "Los Angeles Galaxy"),
        _pair("Club America", "Guadalajara Chivas"),
    }
)

_EXPLICIT_FALSE_PAIRS: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True, slots=True)
class RivalryResult:
    value: int | None
    source: str
    version: str
    quality: str


def rivalry_indicator(home_team: object, away_team: object) -> RivalryResult:
    pair = _pair(str(home_team or ""), str(away_team or ""))
    if pair in _POSITIVE_PAIRS:
        return RivalryResult(1, "static_registry", RIVALRY_REGISTRY_VERSION, "CONFIRMED_RIVALRY")
    if pair in _EXPLICIT_FALSE_PAIRS:
        return RivalryResult(0, "static_registry", RIVALRY_REGISTRY_VERSION, "CONFIRMED_NON_RIVALRY")
    return RivalryResult(None, "static_registry", RIVALRY_REGISTRY_VERSION, "UNKNOWN_COVERAGE")
