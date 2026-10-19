from datetime import UTC, datetime
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from h2h.corner_buckets import CORNER_OPERATIONS_IDS
from h2h.production_buckets import RESEARCH_BTTS_NO_ODDS_2_01_2_50, GOALLAB_OU_OVER_XG_2_5_3_0
from h2h.persistence.postgres_production_funnel import PostgreSQLProductionFunnelRepository as Repository


@pytest.mark.parametrize('buckets,expected',[
    ((RESEARCH_BTTS_NO_ODDS_2_01_2_50,*CORNER_OPERATIONS_IDS),{'research','cornerlab'}),
    ((GOALLAB_OU_OVER_XG_2_5_3_0,),{'goallab'}),
    ((CORNER_OPERATIONS_IDS[0],),{'cornerlab'}),
])
def test_selected_sources_control_history_and_candidate_queries(monkeypatch,buckets,expected):
    calls=[]
    for source in ('research','goallab','cornerlab'):
        monkeypatch.setattr(Repository,'_'+source+'_performance_rows',staticmethod(lambda cursor,s=source:calls.append(s) or ()))
    stats=Repository._bucket_performance(None,bucket_ids=buckets)
    assert set(calls)==expected
    assert all(s['graded_n']==0 for s in stats.values())
    calls.clear()
    repository=Repository(connect=lambda:nullcontext(MagicMock()))
    for source in ('research','goallab','cornerlab'):
        monkeypatch.setattr(repository,'_'+source+'_candidates',lambda *args,s=source,**kw:calls.append(s) or ())
    monkeypatch.setattr(repository,'_open_exposure',lambda cursor:0)
    result=repository.sync(now=datetime(2026,10,20,tzinfo=UTC),max_open_exposure_minor=600000,
                           fallback_stake_minor=30000,currency='RSD',bucket_ids=buckets)
    assert set(calls)==expected
    assert result.cloned_picks==0
