"""Behavioral PostgreSQL checks; TEST_DATABASE_URL must point at a disposable DB."""
from contextlib import nullcontext
from datetime import UTC, datetime
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from h2h.api.dashboard import DashboardService
from h2h.domain.operator_pick_state import OperatorPickState
from h2h.persistence.migrations import apply_migrations
from h2h.persistence.postgres_production_funnel import (
    PostgreSQLProductionFunnelRepository,
    PostgreSQLProductionFunnelStateRepository,
)


@pytest.fixture
def database():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('requires disposable TEST_DATABASE_URL')
    import psycopg
    schema = 'production_test_' + uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA {schema}')
    try:
        connection = psycopg.connect(url, options=f'-c search_path={schema},public')
        apply_migrations(connection, Path(__file__).parents[2] / 'migrations')
        with psycopg.connect(url, options=f'-c search_path={schema},public') as connection:
            yield connection
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA {schema} CASCADE')


def add_pick(connection, number):
    pick_id = 'production-pick-v1:' + f'{number:064x}'
    connection.execute("""
        INSERT INTO production_funnel_picks (
            pick_id,source_universe,source_pick_id,source_fixture_id,
            intake_contract_version,matched_bucket_ids,bucket_priority,
            home_team,away_team,competition_name,country,provider_status,
            market_key,selection,line,bookmaker_name,odds,source_decision_at,
            kickoff_at,cloned_at,stake_minor,currency
        ) VALUES (%s,'CORNERLAB',%s,%s,'test',ARRAY['test'],1,
            'Home','Away','Cup','Austria','NS','TOTAL_CORNERS','OVER',9.5,
            '1xBet',2.2,'2026-10-01','2026-10-30','2026-10-01',30000,'RSD')
        """, (pick_id, 'source-' + str(number), 'fixture-' + str(number)))
    return pick_id


def test_void_is_idempotent_production_only_and_releases_exposure(database):
    pending, played, skipped = [add_pick(database, n) for n in (1, 2, 3)]
    connect = lambda: nullcontext(database)
    repo = PostgreSQLProductionFunnelRepository(connect=connect)
    states = PostgreSQLProductionFunnelStateRepository(connect=connect)
    now = datetime.now(UTC)
    states.set_state(played, OperatorPickState.PLAYED, 'played', occurred_at=now)
    states.set_state(skipped, OperatorPickState.SKIPPED, 'skipped', occurred_at=now)
    assert repo.exposure_breakdown()['open_exposure_minor'] == 60000
    for pick in (pending, played, skipped):
        args = (pick, 'void:' + pick, 'operator', 'User requested VOID')
        database.execute('SELECT production_void_pick(%s,%s,%s,%s)', args)
        database.execute('SELECT production_void_pick(%s,%s,%s,%s)', args)
    assert database.execute('SELECT count(*) FROM production_funnel_voids').fetchone()[0] == 3
    assert states.current_state(pending) is OperatorPickState.PENDING
    assert states.current_state(played) is OperatorPickState.PLAYED
    assert states.current_state(skipped) is OperatorPickState.SKIPPED
    assert repo.exposure_breakdown()['open_exposure_minor'] == 0
    with database.cursor() as cursor:
        assert repo._open_exposure(cursor) == 0
    service = DashboardService(SimpleNamespace(runtime=SimpleNamespace(connect=connect)))
    picks = service._picks()
    assert len(picks) == 1 and picks[0]['pick_id'] == played
    assert picks[0]['settlement_outcome'] == 'VOID'
    assert picks[0]['realized_pnl_minor'] == 0
    assert picks[0]['gross_return_minor'] == 30000
    assert service._is_history_pick(picks[0])
    for table in ('quantlab_shadow_bets', 'quantlab_corner_settlement_events',
                  'research_signals', 'pick_settlement_events', 'bankroll_ledger_entries'):
        assert database.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
    database.execute("INSERT INTO production_funnel_history_resets VALUES "
                     "('reset','operator','Reset production history',CURRENT_TIMESTAMP)")
    database.execute('INSERT INTO production_funnel_archives '
                     '(pick_id,request_id,actor,reason) VALUES (%s,%s,%s,%s)',
                     (played, 'reset', 'operator', 'Reset production history'))
    assert service._picks() == []
    assert database.execute('SELECT count(*) FROM production_funnel_picks').fetchone()[0] == 3


def test_void_conflicting_retry_and_append_only_guards(database):
    import psycopg
    pick = add_pick(database, 1)
    args = (pick, 'request', 'operator', 'reason')
    database.execute('SELECT production_void_pick(%s,%s,%s,%s)', args)
    with pytest.raises(psycopg.Error), database.transaction():
        database.execute('SELECT production_void_pick(%s,%s,%s,%s)',
                         (pick, 'different-request', 'operator', 'reason'))
    with pytest.raises(psycopg.Error), database.transaction():
        database.execute('DELETE FROM production_funnel_voids WHERE pick_id=%s', (pick,))
