from datetime import UTC, datetime

import pytest

from h2h.persistence.postgres_research_signals import (
    PostgreSQLResearchSignalRepository,
    research_signal_id,
)


def test_research_signal_id_is_deterministic_from_evaluation_id() -> None:
    suffix = "a" * 64
    assert research_signal_id("value-evaluation-v1:" + suffix) == "research-signal-v1:" + suffix


@pytest.mark.parametrize("value", ["", "value-evaluation-v1:nope", "pick-v1:" + "a" * 64])
def test_research_signal_id_rejects_non_evaluation_identifiers(value: str) -> None:
    with pytest.raises(ValueError):
        research_signal_id(value)


class _Cursor:
    def __init__(self) -> None:
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        return ("research-signal-v1:" + "a" * 64,)


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


def test_record_exposure_blocked_upserts_by_fixture_not_evaluation() -> None:
    cursor = _Cursor()
    connection = _Connection(cursor)
    repository = PostgreSQLResearchSignalRepository(connect=lambda: connection)
    evaluation_id = "value-evaluation-v1:" + "a" * 64

    signal_id = repository.record_exposure_blocked(
        evaluation_id,
        blocked_at=datetime(2026, 9, 25, 12, tzinfo=UTC),
        open_exposure_minor=300_000,
        exposure_cap_minor=300_000,
    )

    assert signal_id == "research-signal-v1:" + "a" * 64
    assert "evaluation_id, fixture_id" in cursor.query
    assert "SELECT %s, e.evaluation_id, e.fixture_id" in cursor.query
    assert "ON CONFLICT (fixture_id) DO UPDATE" in cursor.query
    assert cursor.params[-1] == evaluation_id


def test_record_production_candidate_upserts_same_fixture_universe() -> None:
    cursor = _Cursor()
    connection = _Connection(cursor)
    repository = PostgreSQLResearchSignalRepository(connect=lambda: connection)
    evaluation_id = "value-evaluation-v1:" + "b" * 64

    signal_id = repository.record_production_candidate(
        evaluation_id,
        qualified_at=datetime(2026, 9, 25, 13, tzinfo=UTC),
        production_pick_id="registered-pick-v1:" + "c" * 64,
    )

    assert signal_id == "research-signal-v1:" + "a" * 64
    assert "qualified_at, production_pick_id" in cursor.query
    assert "ON CONFLICT (fixture_id) DO UPDATE" in cursor.query
    assert "production_pick_id = EXCLUDED.production_pick_id" in cursor.query
    assert cursor.params[-1] == evaluation_id
