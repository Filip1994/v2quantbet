"""Run with COST_TEST_DATABASE_URL pointing to an isolated PostgreSQL database."""
import os
from contextlib import nullcontext
from datetime import datetime, timezone
import psycopg
import pytest
from h2h.quantlab.repository import PostgreSQLQuantLabRepository

LOCAL = os.environ.get("COST_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not LOCAL, reason="isolated PostgreSQL URL required")

def test_opponents():
 with psycopg.connect(LOCAL) as c:
  c.execute('CREATE TEMP TABLE quantlab_fixture_observations(fixture_id text,fixture_observation_id text,home_team_id bigint,away_team_id bigint,kickoff_at timestamptz,captured_at timestamptz,provider_status text)')
  rows=[('normal','a',1,2,'2026-10-01','2026-10-01','FT'),
        ('corrected','a',1,3,'2026-10-02','2026-10-02','FT'),
        ('corrected','b',4,3,'2026-10-02','2026-10-03','FT'),
        ('status','a',1,5,'2026-10-03','2026-10-03','FT'),
        ('status','b',1,5,'2026-10-03','2026-10-04','NS'),
        ('moved','a',1,6,'2026-10-04','2026-10-04','FT'),
        ('moved','b',1,6,'2027-01-01','2026-10-05','NS'),
        ('away','a',7,1,'2026-10-05','2026-10-05','AET'),
        ('null','a',1,None,'2026-10-06','2026-10-06','FT'),
        ('self','a',1,1,'2026-10-06','2026-10-06','FT'),
        ('tie','a',1,8,'2026-10-07','2026-10-07','FT'),
        ('tie','b',1,9,'2026-10-07','2026-10-07','FT')]
  with c.cursor() as cur: cur.executemany('INSERT INTO quantlab_fixture_observations VALUES (%s,%s,%s,%s,%s,%s,%s)',rows)
  repo=PostgreSQLQuantLabRepository(connect=lambda:nullcontext(c))
  result=repo.recent_team_opponent_ids(1,before=datetime(2026,10,18,tzinfo=timezone.utc))
  assert result==(9,7,6,2),result
  assert repo.recent_team_opponent_ids(1,before=datetime(2026,10,18,tzinfo=timezone.utc),limit=2)==(9,7)
  assert repo.recent_team_opponent_ids(0,before=datetime.now(timezone.utc))==()
 print('PASS opponent identity corrections, latest status, historical cutoff, tie order, limit')

