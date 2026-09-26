from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from h2h.quantlab.goal_lab.injuries import build_goal_injury_features
from h2h.quantlab.goal_lab.standings import build_goal_standings_features


NOW = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)


def _standings_payload() -> dict[str, object]:
    rows = []
    points = [20, 18, 16, 14, 10, 7]
    for index, value in enumerate(points, start=1):
        rows.append(
            {
                "rank": index,
                "team": {"id": index, "name": f"Team {index}"},
                "points": value,
                "goalsDiff": 10 - index,
                "all": {
                    "played": 8,
                    "goals": {"for": 16 - index, "against": 6 + index},
                },
            }
        )
    return {"response": [{"league": {"standings": [rows]}}]}


def test_goal_standings_features_are_timestamp_safe_and_complete() -> None:
    features, meta = build_goal_standings_features(
        _standings_payload(),
        home_team_id=1,
        away_team_id=4,
        competition_name="Premier League",
        available_at=NOW - timedelta(hours=2),
        decision_at=NOW,
    )

    assert features["standings_coverage_flag"] == 1.0
    assert features["home_standings_rank"] == 1.0
    assert features["away_standings_rank"] == 4.0
    assert features["standings_rank_differential"] == -3.0
    assert features["home_standings_points"] == 20.0
    assert features["away_standings_points"] == 14.0
    assert features["standings_points_differential"] == 6.0
    assert features["home_distance_to_title_points"] == 0.0
    assert features["away_distance_to_primary_threshold_points"] == 0.0
    assert 0.0 <= features["match_importance_proxy"] <= 1.0
    assert meta["quality"] == "OBSERVED"
    assert meta["table_size"] == 6


def test_goal_standings_features_reject_future_snapshot() -> None:
    with pytest.raises(ValueError, match="after decision_at"):
        build_goal_standings_features(
            _standings_payload(),
            home_team_id=1,
            away_team_id=4,
            competition_name="Premier League",
            available_at=NOW + timedelta(seconds=1),
            decision_at=NOW,
        )


def _injury_capture(response: list[dict[str, object]]) -> dict[str, object]:
    return {
        "injury_capture_id": "injury-1",
        "available_at": NOW - timedelta(hours=1),
        "status": "AVAILABLE",
        "response_item_count": len(response),
        "reason": None,
        "source": "api-football:injuries",
        "raw_payload": {"response": response},
    }


def test_goal_injury_features_distinguish_injury_suspension_and_duplicates() -> None:
    capture = _injury_capture(
        [
            {
                "team": {"id": 10},
                "player": {"id": 100, "type": "Missing Fixture", "reason": "Knee Injury"},
            },
            {
                "team": {"id": 10},
                "player": {"id": 100, "type": "Missing Fixture", "reason": "Knee Injury"},
            },
            {
                "team": {"id": 11},
                "player": {"id": 200, "type": "Missing Fixture", "reason": "Red Card"},
            },
        ]
    )

    features, meta = build_goal_injury_features(
        capture,
        home_team_id=10,
        away_team_id=11,
        decision_at=NOW,
    )

    assert features["injury_coverage_flag"] == 1.0
    assert features["home_unavailable_player_count"] == 1.0
    assert features["away_unavailable_player_count"] == 1.0
    assert features["home_injury_count"] == 1.0
    assert features["home_suspension_count"] == 0.0
    assert features["away_injury_count"] == 0.0
    assert features["away_suspension_count"] == 1.0
    assert meta["home_unique_players"] == 1
    assert meta["away_unique_players"] == 1


def test_valid_empty_injury_response_is_observed_zero_not_missing() -> None:
    features, meta = build_goal_injury_features(
        _injury_capture([]),
        home_team_id=10,
        away_team_id=11,
        decision_at=NOW,
    )

    assert features["injury_coverage_flag"] == 1.0
    assert features["home_unavailable_player_count"] == 0.0
    assert features["away_unavailable_player_count"] == 0.0
    assert features["home_injury_count"] == 0.0
    assert features["away_suspension_count"] == 0.0
    assert meta["quality"] == "OBSERVED"


def test_unavailable_injury_capture_does_not_fabricate_zero_counts() -> None:
    features, meta = build_goal_injury_features(
        {
            "available_at": NOW - timedelta(hours=1),
            "status": "UNAVAILABLE",
            "reason": "league-season-injuries-false",
            "source": "api-football:leagues",
            "raw_payload": {"response": []},
        },
        home_team_id=10,
        away_team_id=11,
        decision_at=NOW,
    )

    assert features == {
        "injury_coverage_flag": 0.0,
        "injury_snapshot_age_days": float("nan"),
    } or (
        features["injury_coverage_flag"] == 0.0
        and "home_unavailable_player_count" not in features
    )
    assert meta["quality"] == "UNAVAILABLE"


def test_goal_injury_features_reject_future_snapshot() -> None:
    capture = _injury_capture([])
    capture["available_at"] = NOW + timedelta(seconds=1)

    with pytest.raises(ValueError, match="after decision_at"):
        build_goal_injury_features(
            capture,
            home_team_id=10,
            away_team_id=11,
            decision_at=NOW,
        )
