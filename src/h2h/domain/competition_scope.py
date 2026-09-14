"""Deterministic Phase I competition-universe policy."""

from dataclasses import dataclass
import re
import unicodedata


class RejectionReason:
    AFRICA = "EXCLUDED_AFRICAN_COMPETITION"
    YOUTH = "EXCLUDED_YOUTH_COMPETITION"
    ENGLISH_TIER = "EXCLUDED_ENGLISH_TIER_4_OR_LOWER"
    GERMAN_TIER = "EXCLUDED_GERMAN_TIER_4_OR_LOWER"
    CUP = "EXCLUDED_CUP_COMPETITION"
    AMBIGUOUS = "AMBIGUOUS_COMPETITION_METADATA"


@dataclass(frozen=True, slots=True)
class CompetitionMetadata:
    """Provider-neutral competition metadata used by the Phase I filter."""

    country: str | None = None
    name: str | None = None
    type: str | None = None
    level: int | None = None


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    eligible: bool
    rejection_reason: str | None = None


def _normalise(value: str | None) -> str:
    value = value or ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def classify_phase_i(metadata: CompetitionMetadata) -> ScopeDecision:
    """Return a fail-closed Phase I inclusion decision."""
    country = _normalise(metadata.country)
    name = _normalise(metadata.name)
    competition_type = _normalise(metadata.type)

    if not country or not name or not competition_type:
        return ScopeDecision(False, RejectionReason.AMBIGUOUS)

    african_markers = {
        "algeria", "angola", "benin", "botswana", "burkina faso", "cameroon",
        "cape verde", "central african republic", "chad", "comoros", "congo",
        "democratic republic of the congo", "djibouti", "egypt", "equatorial guinea",
        "eritrea", "eswatini", "ethiopia", "gabon", "gambia", "ghana", "guinea",
        "guinea bissau", "ivory coast", "kenya", "lesotho", "liberia", "libya",
        "madagascar", "malawi", "mali", "mauritania", "mauritius", "morocco",
        "mozambique", "namibia", "niger", "nigeria", "rwanda", "senegal",
        "seychelles", "sierra leone", "somalia", "south africa", "south sudan",
        "sudan", "tanzania", "togo", "tunisia", "uganda", "zambia", "zimbabwe",
    }
    if country in african_markers or "africa" in country:
        return ScopeDecision(False, RejectionReason.AFRICA)

    youth_pattern = r"\b(?:u|under)\s*\d{2}\b|youth|junior|academy|reserve youth|\bolympic\b"
    if re.search(youth_pattern, name) or re.search(youth_pattern, competition_type):
        return ScopeDecision(False, RejectionReason.YOUTH)

    if "cup" in competition_type or "cup" in name or "knockout" in competition_type:
        return ScopeDecision(False, RejectionReason.CUP)

    if country in {"england", "england uk", "united kingdom"}:
        if name in {"league two", "national league", "national league north", "national league south"}:
            return ScopeDecision(False, RejectionReason.ENGLISH_TIER)
        if metadata.level is not None and metadata.level >= 4:
            return ScopeDecision(False, RejectionReason.ENGLISH_TIER)

    if country == "germany":
        if "regionalliga" in name or (metadata.level is not None and metadata.level >= 4):
            return ScopeDecision(False, RejectionReason.GERMAN_TIER)

    return ScopeDecision(True)
