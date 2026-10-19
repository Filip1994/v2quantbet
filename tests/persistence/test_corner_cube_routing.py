from decimal import Decimal

import pytest

from h2h.corner_buckets import CORNER_OPERATIONS_BUCKETS, CORNER_OPERATIONS_IDS
from h2h.production_buckets import matching_bucket_ids
from h2h.persistence.postgres_production_funnel import active_bucket_ids


def candidate(bucket):
    middle=lambda bounds:sum(Decimal(v) for v in bounds)/2
    return {'market_key': 'TOTAL_CORNERS','selection': bucket.selection,
                'odds': middle(bucket.odds),'model_probability': middle(bucket.probability),
                'expected_value': middle(bucket.ev),'line': Decimal('9.5'),
                'expected_total_corners': Decimal('9.5')+middle(bucket.gap)}


@pytest.mark.parametrize('bucket',CORNER_OPERATIONS_BUCKETS)
def test_seven_exact_disjoint_approved_cubes(bucket):
    row=candidate(bucket)
    matches=set(matching_bucket_ids(row,source_universe='CORNERLAB')) & set(CORNER_OPERATIONS_IDS)
    assert matches == {bucket.bucket_id}


@pytest.mark.parametrize('bucket',CORNER_OPERATIONS_BUCKETS)
@pytest.mark.parametrize('field,range_name',[('odds','odds'),('model_probability','probability'),('expected_value','ev')])
def test_half_open_boundaries(bucket,field,range_name):
    row=candidate(bucket)
    low,high=getattr(bucket,range_name)
    assert bucket.matches({**row,field:Decimal(low)})
    assert not bucket.matches({**row,field:Decimal(high)})


def test_under_n12_cube_is_not_selected_but_under_n13_is_selected():
    excluded={'market_key': 'TOTAL_CORNERS','selection': 'UNDER','odds': '1.65',
                  'model_probability': '.625','expected_value': '.025','line': '10.5','expected_total_corners': '10.0'}
    assert not any(b.matches(excluded) for b in CORNER_OPERATIONS_BUCKETS)
    assert CORNER_OPERATIONS_BUCKETS[1].matches(candidate(CORNER_OPERATIONS_BUCKETS[1]))
    assert len(CORNER_OPERATIONS_IDS)==7


def test_stale_legacy_corner_route_is_disabled():
    from h2h.production_buckets import CORNER_OVER_GAP_1_2_ODDS_1_61_1_80,RESEARCH_BTTS_NO_ODDS_2_01_2_50
    assert active_bucket_ids({'QUANTBET_PRODUCTION_INTAKE_BUCKETS':','.join([
        CORNER_OVER_GAP_1_2_ODDS_1_61_1_80,RESEARCH_BTTS_NO_ODDS_2_01_2_50,*CORNER_OPERATIONS_IDS])}) == (
            RESEARCH_BTTS_NO_ODDS_2_01_2_50,*CORNER_OPERATIONS_IDS)


@pytest.mark.parametrize('bucket', CORNER_OPERATIONS_BUCKETS)
def test_gap_bounds_and_invalid_numbers_fail_closed(bucket):
    row = candidate(bucket)
    low, high = (Decimal(v) for v in bucket.gap)
    assert bucket.matches({**row, 'expected_total_corners': row['line'] + low})
    assert not bucket.matches({**row, 'expected_total_corners': row['line'] + high})
    for value in ('NaN', 'Infinity', None, 'bad'):
        assert not bucket.matches({**row, 'odds': value})


def test_performance_preserves_separate_source_picks_from_same_fixture():
    from h2h.persistence.postgres_production_funnel import PostgreSQLProductionFunnelRepository

    class Cursor:
        description = ()
        def execute(self, query):
            assert 'fixture_rank' not in query
            assert 'ORDER BY e.occurred_at DESC, e.corner_settlement_event_id DESC' in query
        def fetchall(self):
            return []
    assert PostgreSQLProductionFunnelRepository._cornerlab_performance_rows(Cursor()) == ()
