"""Deterministic Phase I competition-universe policy."""

import re
import unicodedata
from dataclasses import dataclass


class RejectionReason:
    AFRICA = "EXCLUDED_AFRICAN_COMPETITION"
    ASIA = "EXCLUDED_ASIAN_COMPETITION"
    YOUTH = "EXCLUDED_YOUTH_COMPETITION"
    WOMEN = "EXCLUDED_WOMENS_FOOTBALL"
    ENGLISH_TIER = "EXCLUDED_ENGLISH_TIER_4_OR_LOWER"
    GERMAN_TIER = "EXCLUDED_GERMAN_TIER_4_OR_LOWER"
    CUP = "EXCLUDED_CUP_COMPETITION"
    EXPLICIT_COMPETITION = "EXCLUDED_EXPLICIT_COMPETITION"
    AMBIGUOUS = "AMBIGUOUS_COMPETITION_METADATA"


@dataclass(frozen=True, slots=True)
class CompetitionMetadata:
    """Provider-neutral competition metadata used by the Phase I filter."""

    country: str | None = None
    name: str | None = None
    type: str | None = None
    level: int | None = None
    home_team: str | None = None
    away_team: str | None = None


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    eligible: bool
    rejection_reason: str | None = None


def _normalise(value: str | None) -> str:
    value = value or ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _contains_phrase(value: str, phrases: tuple[str, ...]) -> bool:
    padded = f" {value} "
    return any(f" {phrase} " in padded for phrase in phrases)


_WOMEN_MARKERS = (
    "women",
    "womens",
    "woman",
    "ladies",
    "female",
    "feminine",
    "feminin",
    "femenina",
    "femenino",
    "femenil",
    "feminino",
    "femminile",
    "frauen",
    "vrouwen",
    "kvinner",
    "kvinnor",
    "kvinde",
    "kobiet",
    "zeny",
    "zene",
    "damer",
    "dames",
)

_WOMEN_ONLY_COMPETITIONS = {
    "nwsl",
    "wsl",
    "liga f",
    "we league",
    "nadeshiko league",
    "damallsvenskan",
    "toppserien",
    "kvindeliga",
}


def is_womens_football(
    *,
    competition_name: object,
    competition_type: object = "",
    home_team: object = "",
    away_team: object = "",
) -> bool:
    """Return True when provider metadata identifies women\'s football.

    Generic single-letter W markers are accepted only as trailing team/competition
    suffixes, avoiding false positives for senior men\'s clubs whose names begin with W.
    """
    competition = _normalise(str(competition_name or ""))
    competition_kind = _normalise(str(competition_type or ""))
    if (
        competition in _WOMEN_ONLY_COMPETITIONS
        or _contains_phrase(competition, _WOMEN_MARKERS)
        or _contains_phrase(competition_kind, _WOMEN_MARKERS)
        or competition.endswith(" w")
    ):
        return True

    for team in (home_team, away_team):
        team_key = _normalise(str(team or ""))
        if _contains_phrase(team_key, _WOMEN_MARKERS) or team_key.endswith(" w"):
            return True
    return False

def classify_phase_i(metadata: CompetitionMetadata) -> ScopeDecision:
    """Return a fail-closed Phase I inclusion decision."""
    country = _normalise(metadata.country)
    name = _normalise(metadata.name)
    competition_type = _normalise(metadata.type)

    if is_womens_football(
        competition_name=metadata.name,
        competition_type=metadata.type,
        home_team=metadata.home_team,
        away_team=metadata.away_team,
    ):
        return ScopeDecision(False, RejectionReason.WOMEN)

    if not country or not name or not competition_type:
        return ScopeDecision(False, RejectionReason.AMBIGUOUS)

    explicitly_excluded_competitions = {
        ("czech republic", "3 liga msfl"),
        ("czechia", "3 liga msfl"),
    }
    if (country, name) in explicitly_excluded_competitions:
        return ScopeDecision(False, RejectionReason.EXPLICIT_COMPETITION)

    african_markers = {
        "algeria", "angola", "benin", "botswana", "burkina faso", "cameroon",
        "cape verde", "central african republic", "chad", "comoros", "congo",
        "democratic republic of the congo", "djibouti", "egypt", "equatorial guinea",
        "eritrea", "eswatini", "ethiopia", "gabon", "gambia", "ghana", "guinea",
        "guinea bissau", "ivory coast", "kenya", "lesotho", "liberia", "libya",
        "burundi", "congo dr", "dr congo", "madagascar", "malawi", "mali",
        "mauritania", "mauritius", "morocco",
        "mozambique", "namibia", "niger", "nigeria", "rwanda", "senegal",
        "sao tome and principe", "seychelles", "sierra leone", "somalia",
        "south africa", "south sudan", "sudan", "tanzania", "togo", "tunisia",
        "uganda", "western sahara", "zambia", "zimbabwe",
    }
    if (
        country in african_markers
        or "africa" in country
        or _contains_phrase(name, ("africa", "caf"))
    ):
        return ScopeDecision(False, RejectionReason.AFRICA)

    asian_markers = {
        "afghanistan", "australia", "bahrain", "bangladesh", "bhutan", "brunei",
        "cambodia", "china", "chinese taipei", "dpr korea", "guam", "hong kong",
        "india", "indonesia", "iran", "iraq", "japan", "jordan", "korea republic",
        "kuwait", "kyrgyzstan", "laos", "lebanon", "macao", "macau", "malaysia",
        "maldives", "mongolia", "myanmar", "nepal", "north korea", "northern mariana islands",
        "oman", "pakistan", "palestine", "philippines", "qatar", "saudi arabia",
        "singapore", "south korea", "sri lanka", "syria", "tajikistan", "thailand",
        "timor leste", "turkmenistan", "uae", "united arab emirates", "uzbekistan",
        "vietnam", "yemen",
    }
    if (
        country in asian_markers
        or country == "asia"
        or _contains_phrase(name, ("asia", "afc"))
    ):
        return ScopeDecision(False, RejectionReason.ASIA)

    youth_pattern = (
        r"\b(?:u|under)\s*\d{1,2}\b|\byouth\b|\bjuniors?\b|\bacademy\b|"
        r"\breserves?\b|\bolympic\b"
    )
    if re.search(youth_pattern, name) or re.search(youth_pattern, competition_type):
        return ScopeDecision(False, RejectionReason.YOUTH)

    cup_markers = (
        "beker",
        "copa",
        "coppa",
        "coupe",
        "cup",
        "pokal",
        "shield",
        "supercup",
        "taca",
        "trophy",
    )
    if (
        _contains_phrase(name, cup_markers)
        or _contains_phrase(competition_type, cup_markers)
        or "knockout" in competition_type
    ):
        return ScopeDecision(False, RejectionReason.CUP)

    if competition_type != "league":
        return ScopeDecision(False, RejectionReason.AMBIGUOUS)

    if country in {"england", "england uk", "united kingdom"}:
        excluded_english_tiers = (
            "counties league",
            "isthmian",
            "league two",
            "national league",
            "non league",
            "northern premier league",
            "southern league",
        )
        if _contains_phrase(name, excluded_english_tiers):
            return ScopeDecision(False, RejectionReason.ENGLISH_TIER)
        if metadata.level is not None and metadata.level >= 4:
            return ScopeDecision(False, RejectionReason.ENGLISH_TIER)

    if country == "germany":
        excluded_german_tiers = (
            "bezirksliga",
            "kreisliga",
            "landesliga",
            "oberliga",
            "regionalliga",
            "verbandsliga",
        )
        if _contains_phrase(name, excluded_german_tiers) or (
            metadata.level is not None and metadata.level >= 4
        ):
            return ScopeDecision(False, RejectionReason.GERMAN_TIER)

    return ScopeDecision(True)
