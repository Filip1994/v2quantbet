from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from h2h.quantlab.goal_lab.picks import (
    choose_canonical_candidate,
    settle_goal_pick,
    stable_goal_result_evidence,
)


NOW = datetime(2026, 9, 27, 0, 30, tzinfo=UTC)


def _candidate(*, ev: float, edge: float, model_p: float, odds: float, market: str, selection: str, bookmaker_id: int):
    return {
        "pair": {
            "bookmaker_id": bookmaker_id,
            "bookmaker_name": "Bet365" if bookmaker_id == 8 else "1xBet",
            "market_key": market,
            "line": 2.5 if market == "OU_25" else None,
        },
        "selection": selection,
        "expected_value": ev,
        "edge": edge,
        "model_probability": model_p,
        "odds": odds,
    }


def test_canonical_candidate_prefers_ev_then_edge_then_model_probability() -> None:
    candidates = (
        _candidate(
            ev=0.08,
            edge=0.07,
            model_p=0.60,
            odds=1.80,
            market="BTTS",
            selection="YES",
            bookmaker_id=8,
        ),
        _candidate(
            ev=0.10,
            edge=0.06,
            model_p=0.58,
            odds=1.90,
            market="OU_25",
            selection="OVER",
            bookmaker_id=11,
        ),
        _candidate(
            ev=0.10,
            edge=0.08,
            model_p=0.57,
            odds=1.88,
            market="OU_25",
            selection="OVER",
            bookmaker_id=8,
        ),
    )

    chosen = choose_canonical_candidate(candidates)

    assert chosen is candidates[2]


def _settlement_row(
    *,
    market_key: str,
    selection: str,
    home: int | None,
    away: int | None,
    classification: str = "PLAYED_SETTLEABLE",
    odds: float = 2.0,
) -> dict[str, object]:
    return {
        "goal_pick_id": "quantlab-goal-pick-v1:" + "a" * 64,
        "fixture_id": "api-football:9001",
        "result_observation_id": "fixture-result-observation-v1:" + "b" * 64,
        "result_classification": classification,
        "provider_status": "FT" if classification == "PLAYED_SETTLEABLE" else "PST",
        "regulation_home_goals": home,
        "regulation_away_goals": away,
        "market_key": market_key,
        "selection": selection,
        "odds": odds,
        "stake_minor": 10_000,
    }


def test_settlement_over_25_win_uses_regulation_score_and_flat_stake() -> None:
    settlement = settle_goal_pick(
        _settlement_row(
            market_key="OU_25",
            selection="OVER",
            home=2,
            away=1,
            odds=1.95,
        ),
        settled_at=NOW,
    )

    assert settlement is not None
    assert settlement.outcome == "WIN"
    assert settlement.pnl_minor == 9_500
    assert settlement.regulation_home_goals == 2
    assert settlement.regulation_away_goals == 1


def test_settlement_under_25_loss() -> None:
    settlement = settle_goal_pick(
        _settlement_row(
            market_key="OU_25",
            selection="UNDER",
            home=2,
            away=1,
        ),
        settled_at=NOW,
    )

    assert settlement is not None
    assert settlement.outcome == "LOSS"
    assert settlement.pnl_minor == -10_000


def test_settlement_btts_no_win() -> None:
    settlement = settle_goal_pick(
        _settlement_row(
            market_key="BTTS",
            selection="NO",
            home=2,
            away=0,
            odds=1.80,
        ),
        settled_at=NOW,
    )

    assert settlement is not None
    assert settlement.outcome == "WIN"
    assert settlement.pnl_minor == 8_000


def test_non_played_terminal_fixture_voids_goal_pick() -> None:
    settlement = settle_goal_pick(
        _settlement_row(
            market_key="OU_25",
            selection="OVER",
            home=None,
            away=None,
            classification="NON_PLAYED_VOIDABLE",
        ),
        settled_at=NOW,
    )

    assert settlement is not None
    assert settlement.outcome == "VOID"
    assert settlement.pnl_minor == 0


def _provider_result_payload(
    *,
    status: str,
    fulltime: tuple[int | None, int | None],
    goals: tuple[int | None, int | None] | None = None,
) -> dict[str, object]:
    result_goals = fulltime if goals is None else goals
    return {
        "fixture": {
            "id": 9001,
            "date": "2026-09-27T18:00:00+00:00",
            "status": {"short": status},
        },
        "teams": {
            "home": {"id": 1, "name": "Home"},
            "away": {"id": 2, "name": "Away"},
        },
        "goals": {"home": result_goals[0], "away": result_goals[1]},
        "score": {
            "fulltime": {"home": fulltime[0], "away": fulltime[1]},
            "extratime": {"home": None, "away": None},
            "penalty": {"home": None, "away": None},
        },
    }


def test_goal_result_requires_two_matching_terminal_confirmations() -> None:
    first = NOW + timedelta(hours=2)
    second = first + timedelta(minutes=15)
    row = {
        "fixture_id": "api-football:9001",
        "latest_result_observation_id": "quantlab-fixture-v1:" + "1" * 64,
        "latest_result_captured_at": second,
        "latest_result_raw_payload": _provider_result_payload(
            status="FT",
            fulltime=(2, 1),
        ),
        "previous_result_observation_id": "quantlab-fixture-v1:" + "2" * 64,
        "previous_result_captured_at": first,
        "previous_result_raw_payload": _provider_result_payload(
            status="FT",
            fulltime=(2, 1),
        ),
    }

    evidence = stable_goal_result_evidence(row)

    assert evidence is not None
    assert evidence["result_classification"] == "PLAYED_SETTLEABLE"
    assert evidence["regulation_home_goals"] == 2
    assert evidence["regulation_away_goals"] == 1
    assert evidence["result_confirmation_count"] == 2


def test_goal_result_does_not_settle_on_changed_terminal_score() -> None:
    first = NOW + timedelta(hours=2)
    second = first + timedelta(minutes=15)
    row = {
        "fixture_id": "api-football:9001",
        "latest_result_observation_id": "quantlab-fixture-v1:" + "3" * 64,
        "latest_result_captured_at": second,
        "latest_result_raw_payload": _provider_result_payload(
            status="FT",
            fulltime=(2, 1),
        ),
        "previous_result_observation_id": "quantlab-fixture-v1:" + "4" * 64,
        "previous_result_captured_at": first,
        "previous_result_raw_payload": _provider_result_payload(
            status="FT",
            fulltime=(1, 1),
        ),
    }

    assert stable_goal_result_evidence(row) is None


def test_goal_result_postponed_is_not_voidable() -> None:
    first = NOW + timedelta(hours=2)
    second = first + timedelta(hours=6)
    postponed = _provider_result_payload(
        status="PST",
        fulltime=(None, None),
        goals=(None, None),
    )
    row = {
        "fixture_id": "api-football:9001",
        "latest_result_observation_id": "quantlab-fixture-v1:" + "5" * 64,
        "latest_result_captured_at": second,
        "latest_result_raw_payload": postponed,
        "previous_result_observation_id": "quantlab-fixture-v1:" + "6" * 64,
        "previous_result_captured_at": first,
        "previous_result_raw_payload": postponed,
    }

    assert stable_goal_result_evidence(row) is None


def _extra_time_payload(*, status: str, fulltime: tuple[int, int],
                        extratime: tuple[int | None, int | None],
                        goals: tuple[int, int],
                        penalty: tuple[int | None, int | None]) -> dict[str, object]:
    payload = _provider_result_payload(status=status, fulltime=fulltime, goals=goals)
    score = payload["score"]
    score["extratime"] = {"home": extratime[0], "away": extratime[1]}
    score["penalty"] = {"home": penalty[0], "away": penalty[1]}
    return payload


def _two_terminal_snapshots(latest, previous=None):
    return {
        "fixture_id": "api-football:9001",
        "latest_result_observation_id": "quantlab-fixture-v1:" + "a" * 64,
        "latest_result_captured_at": NOW + timedelta(hours=3),
        "latest_result_raw_payload": latest,
        "previous_result_observation_id": "quantlab-fixture-v1:" + "b" * 64,
        "previous_result_captured_at": NOW + timedelta(hours=2),
        "previous_result_raw_payload": latest if previous is None else previous,
    }


@pytest.mark.parametrize(
    ("status", "fulltime", "extratime", "goals", "penalty", "market", "selection", "expected"),
    [
        ("PEN", (1, 1), (0, 0), (1, 1), (5, 4), "OU_25", "OVER", "LOSS"),
        ("PEN", (2, 2), (0, 0), (2, 2), (4, 3), "OU_25", "OVER", "WIN"),
        ("PEN", (1, 1), (0, 0), (1, 1), (3, 4), "OU_25", "OVER", "LOSS"),
        ("PEN", (2, 2), (0, 0), (2, 2), (4, 5), "OU_25", "OVER", "WIN"),
        ("AET", (1, 1), (0, 1), (1, 2), (None, None), "OU_25", "UNDER", "WIN"),
        ("PEN", (2, 2), (0, 0), (2, 2), (3, 4), "BTTS", "YES", "WIN"),
        ("PEN", (1, 1), (1, 1), (2, 2), (4, 2), "OU_25", "UNDER", "WIN"),
    ],
)
def test_goal_lab_incremental_extra_time_settlement(
    status, fulltime, extratime, goals, penalty, market, selection, expected
) -> None:
    """Real backlog payload shapes must use 90-minute goals, not shootout/ET totals."""
    payload = _extra_time_payload(
        status=status, fulltime=fulltime, extratime=extratime,
        goals=goals, penalty=penalty,
    )
    evidence = stable_goal_result_evidence(_two_terminal_snapshots(payload))
    assert evidence is not None
    assert (evidence["regulation_home_goals"], evidence["regulation_away_goals"]) == fulltime
    assert evidence["result_normalization_compat_version"] == (
        "GOALLAB_INCREMENTAL_EXTRA_TIME_V1"
    )
    row = {**_settlement_row(
        market_key=market, selection=selection,
        home=fulltime[0], away=fulltime[1],
    ), **evidence}
    settlement = settle_goal_pick(row, settled_at=NOW)
    assert settlement is not None
    assert settlement.outcome == expected
    assert settlement.result_detail["result_confirmation_count"] == 2
    assert settlement.result_detail["result_normalization_compat_version"] == (
        "GOALLAB_INCREMENTAL_EXTRA_TIME_V1"
    )


def test_goal_lab_penalty_missing_shootout_score_stays_unsettled() -> None:
    """Observed fixture 1635982 must remain pending, not be inferred from status."""
    p = _extra_time_payload(
        status="PEN", fulltime=(2, 2), extratime=(None, None),
        goals=(2, 2), penalty=(None, None),
    )
    assert stable_goal_result_evidence(_two_terminal_snapshots(p)) is None


def test_goal_lab_penalty_missing_et_and_prior_zero_et_are_consistent() -> None:
    latest = _extra_time_payload(
        status="PEN", fulltime=(2, 2), extratime=(None, None),
        goals=(2, 2), penalty=(3, 4),
    )
    previous = _extra_time_payload(
        status="PEN", fulltime=(2, 2), extratime=(0, 0),
        goals=(2, 2), penalty=(3, 4),
    )
    evidence = stable_goal_result_evidence(_two_terminal_snapshots(latest, previous))
    assert evidence is not None
    assert (evidence["regulation_home_goals"], evidence["regulation_away_goals"]) == (2, 2)
    assert evidence["result_confirmation_count"] == 2


def test_goal_lab_inconsistent_extra_time_arithmetic_stays_unsettled() -> None:
    payload = _extra_time_payload(
        status="AET", fulltime=(1, 1), extratime=(0, 1),
        goals=(5, 4), penalty=(None, None),
    )
    assert stable_goal_result_evidence(_two_terminal_snapshots(payload)) is None


def test_goal_lab_extra_time_conflicting_90_minute_snapshots_stay_unsettled() -> None:
    latest = _extra_time_payload(
        status="PEN", fulltime=(1, 1), extratime=(0, 0),
        goals=(1, 1), penalty=(4, 5),
    )
    previous = _extra_time_payload(
        status="PEN", fulltime=(2, 2), extratime=(0, 0),
        goals=(2, 2), penalty=(4, 5),
    )
    assert stable_goal_result_evidence(_two_terminal_snapshots(latest, previous)) is None


def test_goal_lab_extra_time_cannot_skip_confirmation_delay() -> None:
    p = _extra_time_payload(
        status="AET", fulltime=(1, 1), extratime=(0, 1),
        goals=(1, 2), penalty=(None, None),
    )
    row = _two_terminal_snapshots(p)
    row["previous_result_captured_at"] = row["latest_result_captured_at"] - timedelta(
        minutes=14
    )
    assert stable_goal_result_evidence(row) is None
