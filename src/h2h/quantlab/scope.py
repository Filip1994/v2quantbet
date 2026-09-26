"""Zero-request league eligibility policy for QuantLab laboratories."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


GOAL_SCOPE_VERSION = "GOAL_SCOPE_V1"
CONTEXT_SCOPE_VERSION = "CARDCORNER_STRONG_LEAGUES_V1"

_AFRICA_COUNTRIES = frozenset(
    {
        "algeria", "angola", "benin", "botswana", "burkina faso", "burundi",
        "cabo verde", "cape verde", "cameroon", "central african republic", "chad",
        "comoros", "congo", "dr congo", "democratic republic of the congo",
        "djibouti", "egypt", "equatorial guinea", "eritrea", "eswatini", "ethiopia",
        "gabon", "gambia", "ghana", "guinea", "guinea bissau", "ivory coast",
        "cote d ivoire", "kenya", "lesotho", "liberia", "libya", "madagascar",
        "malawi", "mali", "mauritania", "mauritius", "morocco", "mozambique",
        "namibia", "niger", "nigeria", "rwanda", "sao tome and principe", "senegal",
        "seychelles", "sierra leone", "somalia", "south africa", "south sudan",
        "sudan", "tanzania", "togo", "tunisia", "uganda", "zambia", "zimbabwe",
    }
)

# "Far East" is intentionally explicit rather than inferred from continents.
_FAR_EAST_COUNTRIES = frozenset(
    {
        "brunei", "cambodia", "china", "chinese taipei", "hong kong", "indonesia",
        "japan", "laos", "macau", "macao", "malaysia", "mongolia", "myanmar",
        "north korea", "philippines", "singapore", "south korea", "taiwan",
        "thailand", "timor leste", "vietnam",
    }
)

_YOUTH_RE = re.compile(r"\b(?:u|under)[ -]?(?:1[3-9]|2[0-3])\b", re.IGNORECASE)
_RESERVE_RE = re.compile(r"\b(?:youth|academy|reserve|reserves|amateur|amateurs)\b", re.IGNORECASE)
_TEAM_SUFFIX_RE = re.compile(r"(?:\s|[-])(?:u17|u18|u19|u20|u21|u23|ii|b)$", re.IGNORECASE)

# Deliberately narrow: these are the competitions for which CardLab/CornerLab
# are allowed to spend fixture-specific provider requests in V1.
_STRONG_LEAGUE_RULES: dict[str, tuple[str, ...]] = {
    "england": ("premier league", "championship"),
    "spain": ("la liga", "segunda division"),
    "italy": ("serie a", "serie b"),
    "germany": ("bundesliga", "2 bundesliga"),
    "france": ("ligue 1",),
    "netherlands": ("eredivisie",),
    "portugal": ("primeira liga",),
    "belgium": ("pro league", "jupiler pro league"),
    "turkey": ("super lig", "super league"),
    "scotland": ("premiership",),
    "austria": ("bundesliga",),
    "switzerland": ("super league",),
    "denmark": ("superliga",),
    "norway": ("eliteserien",),
    "sweden": ("allsvenskan",),
    "czech republic": ("czech liga", "first league", "chance liga"),
    "czechia": ("czech liga", "first league", "chance liga"),
    "poland": ("ekstraklasa",),
    "greece": ("super league 1", "super league"),
    "croatia": ("hnl",),
    "serbia": ("super liga",),
    "romania": ("liga i", "liga 1"),
    "brazil": ("serie a",),
    "argentina": ("liga profesional", "primera division"),
    "usa": ("major league soccer", "mls"),
    "united states": ("major league soccer", "mls"),
    "mexico": ("liga mx",),
}

_STRONG_WORLD_COMPETITIONS = (
    "uefa champions league",
    "uefa europa league",
    "uefa conference league",
    "champions league",
    "europa league",
    "conference league",
)


def _ascii(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _is_youth_or_amateur(*values: object) -> bool:
    joined = " ".join(str(value or "") for value in values)
    return bool(
        _YOUTH_RE.search(joined)
        or _RESERVE_RE.search(joined)
        or any(_TEAM_SUFFIX_RE.search(str(value or "").strip()) for value in values)
    )


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    allowed: bool
    version: str
    reason: str


def goal_scope(
    *,
    country: object,
    competition_name: object,
    competition_type: object = "",
    home_team: object = "",
    away_team: object = "",
) -> ScopeDecision:
    """Return GoalLab eligibility without making a provider request."""
    if _is_youth_or_amateur(competition_name, competition_type, home_team, away_team):
        return ScopeDecision(False, GOAL_SCOPE_VERSION, "youth_or_amateur")
    country_key = _ascii(country)
    competition_key = _ascii(competition_name)
    if country_key in _AFRICA_COUNTRIES or " caf " in f" {competition_key} " or "africa" in competition_key:
        return ScopeDecision(False, GOAL_SCOPE_VERSION, "africa")
    if country_key in _FAR_EAST_COUNTRIES:
        return ScopeDecision(False, GOAL_SCOPE_VERSION, "far_east")
    return ScopeDecision(True, GOAL_SCOPE_VERSION, "eligible")


def card_corner_scope(
    *,
    country: object,
    competition_name: object,
    competition_type: object = "",
    home_team: object = "",
    away_team: object = "",
) -> ScopeDecision:
    """Restrict CardLab/CornerLab provider spend to a deterministic strong-league set."""
    if _is_youth_or_amateur(competition_name, competition_type, home_team, away_team):
        return ScopeDecision(False, CONTEXT_SCOPE_VERSION, "youth_or_amateur")
    country_key = _ascii(country)
    competition_key = _ascii(competition_name)
    if any(token in competition_key for token in _STRONG_WORLD_COMPETITIONS):
        return ScopeDecision(True, CONTEXT_SCOPE_VERSION, "strong_world_competition")
    for token in _STRONG_LEAGUE_RULES.get(country_key, ()):
        if token in competition_key:
            return ScopeDecision(True, CONTEXT_SCOPE_VERSION, "strong_league")
    return ScopeDecision(False, CONTEXT_SCOPE_VERSION, "outside_strong_league_allowlist")


def eligible_labs(**fixture: object) -> tuple[str, ...]:
    labs: list[str] = []
    if goal_scope(**fixture).allowed:
        labs.append("GOAL")
    if card_corner_scope(**fixture).allowed:
        labs.extend(("CORNER", "CARD"))
    return tuple(labs)
