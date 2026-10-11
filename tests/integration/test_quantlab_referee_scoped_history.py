"""SQL parity coverage for scoped CardLab referee history.

Uses PostgreSQL's session-local TEMP tables, never production data or migrations.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from h2h.quantlab.repository import PostgreSQLQuantLabRepository

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = os.environ.get("QUANTBET_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="QUANTBET_TEST_DATABASE_URL is required for referee SQL parity",
)


def test_scoped_referee_history_returns_correct_as_of_statistics() -> None:
    assert DATABASE_URL is not None
    now = datetime(2026, 10, 11, 0, tzinfo=UTC)
    kickoff = now - timedelta(days=1)
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "CREATE TEMP TABLE quantlab_fixture_context_observations ("
            "fixture_id TEXT, referee TEXT, kickoff_at timestamptz, "
            "available_at timestamptz, context_observation_id TEXT)"
        )
        connection.execute(
            "CREATE TEMP TABLE quantlab_match_statistics_observations ("
            "fixture_id TEXT, available_at timestamptz, "
            "statistics_observation_id TEXT, home_fouls INT, away_fouls INT, "
            "home_yellow_cards INT, away_yellow_cards INT, "
            "home_red_cards INT, away_red_cards INT, "
            "home_second_yellow_cards INT, away_second_yellow_cards INT)"
        )
        connection.execute(
            "CREATE TEMP TABLE quantlab_card_event_observations ("
            "fixture_id TEXT, available_at timestamptz, "
            "card_event_observation_id TEXT, total_cards_1xbet INT)"
        )
        connection.execute("SET search_path = pg_temp, public")

        for fixture, referee in (("fixture-a", "Ref A, England"), ("fixture-b", "Ref B")):
            connection.execute(
                "INSERT INTO quantlab_fixture_context_observations "
                "(fixture_id, referee, kickoff_at, available_at, context_observation_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (fixture, referee, kickoff, kickoff + timedelta(hours=1), "ctx-1"),
            )

        for fixture, sid, hours, yellow, fouls in (
            ("fixture-a", "old", 2, (1, 2), (10, 11)),
            ("fixture-a", "current", 3, (2, 3), (13, 17)),
            ("fixture-b", "unrelated", 3, (20, 30), (50, 60)),
        ):
            connection.execute(
                "INSERT INTO quantlab_match_statistics_observations "
                "(fixture_id, available_at, statistics_observation_id, "
                "home_fouls, away_fouls, home_yellow_cards, away_yellow_cards, "
                "home_red_cards, away_red_cards, "
                "home_second_yellow_cards, away_second_yellow_cards) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 1, 0, 0)",
                (
                    fixture,
                    kickoff + timedelta(hours=hours),
                    sid,
                    *fouls,
                    *yellow,
                ),
            )

        connection.execute(
            "INSERT INTO quantlab_card_event_observations "
            "(fixture_id, available_at, card_event_observation_id, total_cards_1xbet) "
            "VALUES (%s, %s, 'evt', 7)",
            ("fixture-a", kickoff + timedelta(hours=4)),
        )
        connection.execute(
            "INSERT INTO quantlab_match_statistics_observations "
            "(fixture_id, available_at, statistics_observation_id, "
            "home_fouls, away_fouls, home_yellow_cards, away_yellow_cards, "
            "home_red_cards, away_red_cards, "
            "home_second_yellow_cards, away_second_yellow_cards) "
            "VALUES ('fixture-a', %s, 'future', 90, 90, 90, 90, 0, 0, 0, 0)",
            (now + timedelta(hours=1),),
        )

        class ExistingConnection:
            def __enter__(self):
                return connection

            def __exit__(self, *_args):
                return False

        repository = PostgreSQLQuantLabRepository(
            connect=lambda: ExistingConnection()
        )
        rows = repository.referee_history("Ref A", decision_at=now)
        assert len(rows) == 1
        assert rows[0]["referee"] == "Ref A, England"
        assert rows[0]["yellow_cards"] == 5
        assert rows[0]["red_cards"] == 1
        assert rows[0]["fouls"] == 30
        assert rows[0]["card_total"] == 7
        assert rows[0]["available_at"] == kickoff + timedelta(hours=4)

        early_rows = repository.referee_history(
            "Ref A, France",
            decision_at=kickoff + timedelta(hours=2, minutes=30),
        )
        assert len(early_rows) == 1
        assert early_rows[0]["yellow_cards"] == 3
        assert early_rows[0]["card_total"] is None
