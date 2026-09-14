from h2h.domain.competition_scope import (
    CompetitionMetadata,
    RejectionReason,
    classify_phase_i,
)


def test_accepts_senior_non_cup_competition():
    assert classify_phase_i(CompetitionMetadata("England", "Premier League", "League", 1)).eligible


def test_rejects_african_competition():
    decision = classify_phase_i(CompetitionMetadata("South Africa", "Premier Soccer League", "League", 1))
    assert decision.rejection_reason == RejectionReason.AFRICA


def test_rejects_youth_competition():
    decision = classify_phase_i(CompetitionMetadata("Spain", "Primera Division U19", "League", 1))
    assert decision.rejection_reason == RejectionReason.YOUTH


def test_rejects_cup_competition():
    decision = classify_phase_i(CompetitionMetadata("England", "FA Cup", "Cup", 1))
    assert decision.rejection_reason == RejectionReason.CUP


def test_rejects_english_fourth_tier():
    decision = classify_phase_i(CompetitionMetadata("England", "League Two", "League", 4))
    assert decision.rejection_reason == RejectionReason.ENGLISH_TIER


def test_rejects_german_regionalliga():
    decision = classify_phase_i(CompetitionMetadata("Germany", "Regionalliga West", "League", 4))
    assert decision.rejection_reason == RejectionReason.GERMAN_TIER


def test_fails_closed_on_missing_metadata():
    decision = classify_phase_i(CompetitionMetadata("France", "", "League", 1))
    assert decision.rejection_reason == RejectionReason.AMBIGUOUS
