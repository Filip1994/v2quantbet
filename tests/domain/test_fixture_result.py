from datetime import UTC, datetime

import pytest

from h2h.domain.fixture_result import (
    ApiFootballSettlementResultNormalizer,
    ResultClassification,
)


NOW = datetime(2026, 9, 16, 15, tzinfo=UTC)


def payload(status="FT", *, goals=(2, 1), fulltime=(2, 1), extratime=(None, None), penalty=(None, None)):
    def pair(values):
        return {"home": values[0], "away": values[1]}

    return {
        "fixture": {
            "id": 42,
            "date": "2026-09-16T12:00:00+00:00",
            "status": {"short": status, "long": status},
        },
        "league": {"id": 39, "season": 2026},
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "goals": pair(goals),
        "score": {
            "halftime": pair((1, 0)),
            "fulltime": pair(fulltime),
            "extratime": pair(extratime),
            "penalty": pair(penalty),
        },
    }


@pytest.mark.parametrize(
    ("status", "goals", "fulltime", "extratime", "penalty"),
    [
        ("FT", (2, 1), (2, 1), (None, None), (None, None)),
        ("AET", (3, 2), (1, 1), (3, 2), (None, None)),
        ("PEN", (1, 1), (1, 1), (1, 1), (5, 4)),
        ("PEN", (1, 1), (1, 1), (None, None), (5, 4)),
    ],
)
def test_completed_statuses_use_only_fulltime(status, goals, fulltime, extratime, penalty):
    result = ApiFootballSettlementResultNormalizer().normalize(
        payload(status, goals=goals, fulltime=fulltime, extratime=extratime, penalty=penalty),
        fixture_id="api-football:42",
        acquired_at=NOW,
    )
    assert result.classification is ResultClassification.PLAYED_SETTLEABLE
    assert result.regulation_goals == fulltime
    assert result.settlement_fingerprint


@pytest.mark.parametrize("status", ["CANC", "ABD", "AWD", "WO"])
def test_nonplayed_terminal_statuses_are_voidable(status):
    result = ApiFootballSettlementResultNormalizer().normalize(
        payload(status, goals=(None, None), fulltime=(None, None)),
        fixture_id="api-football:42",
        acquired_at=NOW,
    )
    assert result.classification is ResultClassification.NON_PLAYED_VOIDABLE
    assert result.regulation_goals == (None, None)


@pytest.mark.parametrize(
    "status", ["PST", "SUSP", "INT", "TBD", "NS", "1H", "HT", "2H", "ET", "BT", "P", "LIVE"]
)
def test_nonterminal_statuses_never_produce_settlement_candidate(status):
    result = ApiFootballSettlementResultNormalizer().normalize(
        payload(status, goals=(None, None), fulltime=(None, None)),
        fixture_id="api-football:42",
        acquired_at=NOW,
    )
    assert result.classification is ResultClassification.NON_TERMINAL
    assert result.settlement_fingerprint is None


def test_unknown_status_is_persistable_but_not_settleable():
    result = ApiFootballSettlementResultNormalizer().normalize(
        payload("MYSTERY", goals=(None, None), fulltime=(None, None)),
        fixture_id="api-football:42",
        acquired_at=NOW,
    )
    assert result.classification is ResultClassification.UNKNOWN_STATUS


@pytest.mark.parametrize(
    "value",
    [
        payload("FT", goals=(2, 1), fulltime=(1, 1)),
        payload("FT", goals=(2, 1), fulltime=(2, 1), extratime=(2, 1)),
        payload("AET", goals=(3, 2), fulltime=(1, 1), extratime=(2, 1)),
        payload("PEN", goals=(1, 1), fulltime=(1, 1), penalty=(None, None)),
    ],
)
def test_malformed_or_contradictory_terminal_scores_are_invalid(value):
    result = ApiFootballSettlementResultNormalizer().normalize(
        value, fixture_id="api-football:42", acquired_at=NOW
    )
    assert result.classification is ResultClassification.INVALID_TERMINAL
    assert result.settlement_fingerprint is None


def test_identical_content_has_identical_identity_and_changed_content_does_not():
    normalizer = ApiFootballSettlementResultNormalizer()
    first = normalizer.normalize(payload(), fixture_id="api-football:42", acquired_at=NOW)
    replay = normalizer.normalize(payload(), fixture_id="api-football:42", acquired_at=NOW)
    changed = normalizer.normalize(
        payload(goals=(3, 1), fulltime=(3, 1)),
        fixture_id="api-football:42",
        acquired_at=NOW,
    )
    assert first.result_observation_id == replay.result_observation_id
    assert first.result_observation_id != changed.result_observation_id

