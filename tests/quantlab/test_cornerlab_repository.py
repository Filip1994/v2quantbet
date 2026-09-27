from datetime import UTC, datetime

from h2h.quantlab.corner_lab.settlement import CornerShadowSettlement
from h2h.quantlab.repository import PostgreSQLQuantLabRepository


NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


class _Cursor:
    def __init__(self) -> None:
        self.query = ""
        self.params = None
        self.rowcount = 1
        self.description = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


def test_corner_settlement_repository_appends_event_without_mutating_shadow_bet() -> None:
    cursor = _Cursor()
    repository = PostgreSQLQuantLabRepository(connect=lambda: _Connection(cursor))
    settlement = CornerShadowSettlement(
        shadow_bet_id="quantlab-shadow-v1:" + "a" * 64,
        fixture_id="api-football:123",
        result_observation_id="fixture-result-observation-v1:" + "b" * 64,
        statistics_observation_id="quantlab-stats-v1:" + "c" * 64,
        outcome="WIN",
        pnl_minor=10_000,
        settled_at=NOW,
        settlement_rule_version="CORNERLAB_TOTAL_CORNERS_HALF_LINE_SETTLEMENT_V1",
        result_detail={
            "result_classification": "PLAYED_SETTLEABLE",
            "actual_total_corners": 11,
        },
    )

    assert repository.save_corner_settlement_event(settlement) is True
    assert "INSERT INTO quantlab_corner_settlement_events" in cursor.query
    assert "UPDATE quantlab_shadow_bets" not in cursor.query
    assert "'NORMAL'" in cursor.query
    assert cursor.params[1] == settlement.shadow_bet_id
    assert cursor.params[3] == settlement.result_observation_id


def test_corner_settlement_candidates_do_not_depend_on_production_result_tracking() -> None:
    cursor = _Cursor()
    repository = PostgreSQLQuantLabRepository(connect=lambda: _Connection(cursor))

    assert repository.corner_shadow_settlement_candidates(limit=25) == ()
    assert "FROM quantlab_fixture_observations o" in cursor.query
    assert "fixture_result_acquisition_states" not in cursor.query
    assert "fixture_result_observations" not in cursor.query
    assert "('FT', 'AET', 'PEN')" in cursor.query
    assert "('CANC', 'ABD', 'AWD', 'WO')" in cursor.query
    assert cursor.params == (25,)
