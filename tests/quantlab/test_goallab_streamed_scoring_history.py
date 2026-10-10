"""Parity and bounded-memory contract for streamed pinned GoalLab history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from h2h.quantlab.goal_lab.model import _build_scoring_context
from h2h.quantlab.repository import PostgreSQLQuantLabRepository

NOW = datetime(2026, 10, 10, 21, tzinfo=UTC)


def _fixture(fixture_id: str, kickoff_at: datetime) -> dict:
    return {
        "fixture_id": fixture_id, "kickoff_at": kickoff_at,
        "home_team_id": 11, "away_team_id": 22, "league_id": 33,
        "season": 2026, "home_goals": 2, "away_goals": 1,
        "player_status": None, "player_payload": None,
    }


def test_streamed_scoring_context_matches_legacy_materialized_context() -> None:
    rows = (
        _fixture("late", NOW - timedelta(days=1)),
        _fixture("early", NOW - timedelta(days=3)),
        _fixture("middle", NOW - timedelta(days=2)),
    )
    reference = _build_scoring_context(rows)
    ordered = sorted(rows, key=lambda row: (row["kickoff_at"], row["fixture_id"]))
    observed = _build_scoring_context(iter(ordered), already_sorted=True)
    assert observed == reference
    assert observed[3] == 3


def test_stream_retrieves_recent_limit_in_bounded_batches() -> None:
    columns = tuple(_fixture("a", NOW))
    queued = [
        tuple(_fixture("early", NOW - timedelta(days=2)).values()),
        tuple(_fixture("late", NOW - timedelta(days=1)).values()),
    ]

    class Cursor:
        description = [SimpleNamespace(name=key) for key in columns]

        def __init__(self):
            self.query = ""
            self.params = None
            self.batch_sizes = []
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self.closed = True

        def execute(self, sql, params):
            self.query = sql
            self.params = params

        def fetchmany(self, size):
            self.batch_sizes.append(size)
            result, queued[:] = queued[:size], queued[size:]
            return result

    class Connection:
        def __init__(self):
            self.cursor_obj = Cursor()
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self.closed = True

        def cursor(self, *, name):
            assert name == "quantlab_goal_scoring_history"
            return self.cursor_obj

    conn = Connection()
    repo = PostgreSQLQuantLabRepository(connect=lambda: conn)
    with repo.stream_goal_scoring_history(before=NOW, limit=30_000, batch_size=1) as rows:
        assert [row["fixture_id"] for row in rows] == ["early", "late"]

    assert conn.closed and conn.cursor_obj.closed
    assert conn.cursor_obj.batch_sizes == [1, 1, 1]
    assert conn.cursor_obj.params == (NOW, NOW, 30_000, NOW, NOW)
    assert "ORDER BY kickoff_at DESC, fixture_id DESC LIMIT %s" in conn.cursor_obj.query
    assert "ORDER BY f.kickoff_at ASC, f.fixture_id ASC" in conn.cursor_obj.query
    assert "pc.raw_payload AS player_payload" in conn.cursor_obj.query


@pytest.mark.parametrize("limit,batch_size", [(0, 128), (128, 0), (-1, 128)])
def test_stream_rejects_invalid_limits(limit: int, batch_size: int) -> None:
    repo = PostgreSQLQuantLabRepository(connect=lambda: None)
    with pytest.raises(ValueError, match="positive"):
        with repo.stream_goal_scoring_history(
            before=NOW, limit=limit, batch_size=batch_size
        ):
            pass
