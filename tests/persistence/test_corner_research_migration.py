"""Run with CORNER_TEST_DATABASE_URL pointing only at an isolated test database."""
import os
from datetime import timedelta
from pathlib import Path

import pytest


def test_additive_migration_backfill_forward_and_no_execution():
    url = os.getenv('CORNER_TEST_DATABASE_URL')
    if not url:
        pytest.skip('isolated PostgreSQL is required')
    import psycopg
    with psycopg.connect(url) as c:
        c.execute('CREATE SCHEMA corner_migration_test')
        c.execute('SET LOCAL search_path=corner_migration_test')
        c.execute('CREATE TABLE quantlab_shadow_bets(shadow_bet_id text primary key, lab text, decision_at timestamptz, created_at timestamptz default now())')
        c.execute("INSERT INTO quantlab_shadow_bets VALUES ('history','CORNER',now()-interval '1 day',now()-interval '1 day')")
        c.execute(Path('migrations/071_cornerlab_research.sql').read_text())
        activation = c.execute('SELECT activated_at FROM research_corner_activation').fetchone()[0]
        c.execute("INSERT INTO quantlab_shadow_bets(shadow_bet_id,lab,decision_at) VALUES ('new','CORNER',%s),('late','CORNER',%s),('football','GOAL',%s)", (activation+timedelta(seconds=1), activation-timedelta(days=1), activation))
        assert c.execute('SELECT source_shadow_bet_id,cohort FROM research_corner_signals ORDER BY 1').fetchall() == [('history','HISTORICAL'),('late','HISTORICAL'),('new','FORWARD')]
        assert c.execute('SELECT bool_or(execution_enabled) FROM research_corner_signals').fetchone()[0] is False
        with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
            c.execute("UPDATE research_corner_signals SET disposition='PLAYED'")
        with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
            c.execute('UPDATE research_corner_signals SET execution_enabled=true')
        with pytest.raises(psycopg.errors.ForeignKeyViolation), c.transaction():
            c.execute("DELETE FROM quantlab_shadow_bets WHERE shadow_bet_id='history'")
        c.rollback()
