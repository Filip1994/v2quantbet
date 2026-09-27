from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from h2h.quantlab.goal_lab.players import (
    PlayerMatchSample,
    parse_goal_player_match_samples,
    projected_team_player_features,
)


NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def _payload() -> dict[str, object]:
    return {
        "response": [
            {
                "team": {"id": 10},
                "players": [
                    {
                        "player": {"id": 100},
                        "statistics": [
                            {
                                "games": {
                                    "minutes": 90,
                                    "position": "F",
                                    "rating": "7.5",
                                    "substitute": False,
                                },
                                "shots": {"total": 4, "on": 2},
                                "goals": {"total": 1, "assists": 1},
                                "passes": {"key": 3},
                                "tackles": {"total": 1, "interceptions": 0},
                                "duels": {"total": 8, "won": 5},
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_completed_player_parser_preserves_only_played_eligible_team_rows() -> None:
    rows = parse_goal_player_match_samples(
        _payload(),
        fixture_id="api-football:1",
        kickoff_at=NOW - timedelta(days=2),
        eligible_team_ids={10, 11},
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.team_id == 10
    assert row.player_id == 100
    assert row.starter is True
    assert row.minutes == 90
    assert row.rating == pytest.approx(7.5)
    assert row.goals == 1
    assert row.assists == 1
    assert row.key_passes == 3


def test_projected_player_features_use_only_matches_before_target() -> None:
    past = PlayerMatchSample(
        fixture_id="past",
        kickoff_at=NOW - timedelta(days=2),
        team_id=10,
        player_id=100,
        minutes=90.0,
        starter=True,
        position="F",
        rating=8.0,
        shots=4.0,
        shots_on_target=2.0,
        goals=1.0,
        assists=1.0,
        key_passes=2.0,
        tackles=1.0,
        interceptions=0.0,
        duels=6.0,
        duels_won=4.0,
    )
    future = PlayerMatchSample(
        fixture_id="future-target",
        kickoff_at=NOW + timedelta(hours=1),
        team_id=10,
        player_id=999,
        minutes=90.0,
        starter=True,
        position="F",
        rating=10.0,
        shots=20.0,
        shots_on_target=20.0,
        goals=10.0,
        assists=10.0,
        key_passes=20.0,
        tackles=10.0,
        interceptions=10.0,
        duels=20.0,
        duels_won=20.0,
    )

    features, meta = projected_team_player_features(
        [past, future],
        prefix="home",
        target_kickoff=NOW,
    )

    assert features["home_player_stats_coverage_flag"] == 1.0
    assert features["home_projected_xi_count"] == 1.0
    assert features["home_projected_xi_rolling_rating"] == pytest.approx(8.0)
    assert features["home_projected_xi_goals_assists_per90"] == pytest.approx(2.0)
    assert meta["projected_player_ids"] == (100,)
    assert 999 not in meta["projected_player_ids"]
