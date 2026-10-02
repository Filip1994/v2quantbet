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
    GERMAN_TIER = "EXCLUDED_GERMAN_TIER_3_OR_LOWER"
    CUP = "EXCLUDED_CUP_COMPETITION"
    EXPLICIT_COMPETITION = "EXCLUDED_EXPLICIT_COMPETITION"
    BLACKLISTED_LEAGUE = "EXCLUDED_BLACKLISTED_LEAGUE"
    BLOCKED_COUNTRY = "EXCLUDED_BLOCKED_COUNTRY"
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
    league_id: int | None = None


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


BLACKLISTED_API_FOOTBALL_LEAGUE_IDS = frozenset({72, 75, 236, 595})
BLOCKED_COUNTRIES = frozenset({"bolivia", "ecuador", "ireland", "republic of ireland"})


def is_blacklisted_country(country: object) -> bool:
    """Return True for countries disabled across the entire football universe."""
    return _normalise(str(country or "")) in BLOCKED_COUNTRIES


def is_blacklisted_league_id(league_id: object) -> bool:
    """Return True for globally disabled API-Football league IDs."""
    if isinstance(league_id, bool):
        return False
    try:
        parsed = int(league_id)
    except (TypeError, ValueError):
        return False
    return parsed in BLACKLISTED_API_FOOTBALL_LEAGUE_IDS


def blocked_domestic_tier_reason(
    *,
    country: object,
    competition_name: object,
    level: object = None,
) -> str | None:
    """Return the shared hard-block reason for low English/German domestic tiers."""
    country_key = _normalise(str(country or ""))
    name_key = _normalise(str(competition_name or ""))

    parsed_level: int | None = None
    if level is not None and not isinstance(level, bool):
        try:
            parsed_level = int(level)
        except (TypeError, ValueError):
            parsed_level = None

    if country_key in {"england", "england uk", "united kingdom"}:
        excluded_english_tiers = (
            "counties league",
            "isthmian",
            "league two",
            "national league",
            "non league",
            "northern premier league",
            "southern league",
        )
        if _contains_phrase(name_key, excluded_english_tiers) or (
            parsed_level is not None and parsed_level >= 4
        ):
            return RejectionReason.ENGLISH_TIER

    if country_key == "germany":
        excluded_german_tiers = (
            "3 liga",
            "bezirksliga",
            "kreisliga",
            "landesliga",
            "oberliga",
            "regionalliga",
            "verbandsliga",
        )
        if _contains_phrase(name_key, excluded_german_tiers) or (
            parsed_level is not None and parsed_level >= 3
        ):
            return RejectionReason.GERMAN_TIER

    return None


def is_blocked_domestic_tier(
    *,
    country: object,
    competition_name: object,
    level: object = None,
) -> bool:
    """Return True when the shared domestic-tier hard gate rejects a league."""
    return blocked_domestic_tier_reason(
        country=country,
        competition_name=competition_name,
        level=level,
    ) is not None


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
    """Return True when provider metadata identifies women's football.

    Generic single-letter W markers are accepted only as trailing team/competition
    suffixes, avoiding false positives for senior men's clubs whose names begin with W.
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


def universe_block_reason(
    *,
    country: object,
    competition_name: object,
    league_id: object = None,
    competition_type: object = "",
    home_team: object = "",
    away_team: object = "",
    level: object = None,
) -> str | None:
    """Return the shared hard-block reason used across the football universe."""
    if is_blacklisted_country(country):
        return RejectionReason.BLOCKED_COUNTRY
    if is_blacklisted_league_id(league_id):
        return RejectionReason.BLACKLISTED_LEAGUE
    if is_womens_football(
        competition_name=competition_name,
        competition_type=competition_type,
        home_team=home_team,
        away_team=away_team,
    ):
        return RejectionReason.WOMEN
    return blocked_domestic_tier_reason(
        country=country,
        competition_name=competition_name,
        level=level,
    )


def is_universe_blocked_competition(
    *,
    country: object,
    competition_name: object,
    league_id: object = None,
    competition_type: object = "",
    home_team: object = "",
    away_team: object = "",
    level: object = None,
) -> bool:
    """Return True for competitions disabled before collection/modeling/analytics."""
    return universe_block_reason(
        country=country,
        competition_name=competition_name,
        league_id=league_id,
        competition_type=competition_type,
        home_team=home_team,
        away_team=away_team,
        level=level,
    ) is not None

def classify_phase_i(metadata: CompetitionMetadata) -> ScopeDecision:
    """Return a fail-closed Phase I inclusion decision."""
    country = _normalise(metadata.country)
    name = _normalise(metadata.name)
    competition_type = _normalise(metadata.type)

    universe_rejection = universe_block_reason(
        country=metadata.country,
        competition_name=metadata.name,
        league_id=metadata.league_id,
        competition_type=metadata.type,
        home_team=metadata.home_team,
        away_team=metadata.away_team,
        level=metadata.level,
    )
    if universe_rejection is not None:
        return ScopeDecision(False, universe_rejection)

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

    return ScopeDecision(True)
