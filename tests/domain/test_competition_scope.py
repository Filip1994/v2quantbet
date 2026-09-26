import pytest

from h2h.domain.competition_scope import (
    CompetitionMetadata,
    RejectionReason,
    classify_phase_i,
)


@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata("England", "Premier League", "league", 1),
        CompetitionMetadata("Spain", "La Liga", "league", 1),
        CompetitionMetadata("Italy", "Serie A", "league", 1),
        CompetitionMetadata("Germany", "Bundesliga", "league", 1),
        CompetitionMetadata("USA", "Major League Soccer", "league", 1),
    ],
)
def test_accepts_representative_senior_leagues(metadata: CompetitionMetadata) -> None:
    assert classify_phase_i(metadata).eligible


@pytest.mark.parametrize(
    ("metadata", "reason"),
    [
        (
            CompetitionMetadata("England", "EFL Trophy", "league"),
            RejectionReason.CUP,
        ),
        (
            CompetitionMetadata("Netherlands", "KNVB Beker", "league"),
            RejectionReason.CUP,
        ),
        (
            CompetitionMetadata("Chile", "Copa Chile", "league"),
            RejectionReason.CUP,
        ),
        (
            CompetitionMetadata("Italy", "Coppa Italia", "league"),
            RejectionReason.CUP,
        ),
        (
            CompetitionMetadata("England", "Non League Premier - Isthmian", "league"),
            RejectionReason.ENGLISH_TIER,
        ),
        (
            CompetitionMetadata("Germany", "Oberliga - Bremen", "league"),
            RejectionReason.GERMAN_TIER,
        ),
        (
            CompetitionMetadata("Spain", "Primera Division U19", "league"),
            RejectionReason.YOUTH,
        ),
        (
            CompetitionMetadata("Argentina", "Reserve League", "league"),
            RejectionReason.YOUTH,
        ),
        (
            CompetitionMetadata("South Africa", "Premier Soccer League", "league"),
            RejectionReason.AFRICA,
        ),
        (
            CompetitionMetadata("World", "CAF Champions League", "league"),
            RejectionReason.AFRICA,
        ),
        (
            CompetitionMetadata("Japan", "J1 League", "league"),
            RejectionReason.ASIA,
        ),
        (
            CompetitionMetadata("Saudi-Arabia", "Pro League", "league"),
            RejectionReason.ASIA,
        ),
        (
            CompetitionMetadata("Australia", "A-League", "league"),
            RejectionReason.ASIA,
        ),
        (
            CompetitionMetadata("World", "AFC Champions League", "league"),
            RejectionReason.ASIA,
        ),
        (
            CompetitionMetadata("England", "League Two", "league", 4),
            RejectionReason.ENGLISH_TIER,
        ),
        (
            CompetitionMetadata("Germany", "Regionalliga West", "league", 4),
            RejectionReason.GERMAN_TIER,
        ),
        (
            CompetitionMetadata("Czech-Republic", "3. liga - MSFL", "league", 3),
            RejectionReason.EXPLICIT_COMPETITION,
        ),
    ],
)
def test_rejects_real_provider_exclusions(
    metadata: CompetitionMetadata, reason: str
) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == reason


@pytest.mark.parametrize(
    "metadata",
    [
        CompetitionMetadata("France", "", "league", 1),
        CompetitionMetadata("France", "Ligue 1", "", 1),
        CompetitionMetadata("France", "Ligue 1", "tournament", 1),
    ],
)
def test_fails_closed_on_ambiguous_metadata(metadata: CompetitionMetadata) -> None:
    decision = classify_phase_i(metadata)

    assert decision.eligible is False
    assert decision.rejection_reason == RejectionReason.AMBIGUOUS
