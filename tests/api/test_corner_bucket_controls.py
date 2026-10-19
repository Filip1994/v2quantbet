from h2h.api.corner_analytics import build_snapshot, render, sorted_bucket_rows
from test_corner_research import source,NOW
from h2h.corner_buckets import CORNER_OPERATIONS_BUCKETS


def test_highlighted_table_represents_same_seven_rules_and_filters_exact_source(monkeypatch):
    b=CORNER_OPERATIONS_BUCKETS[1]
    monkeypatch.setenv('QUANTBET_PRODUCTION_INTAKE_BUCKETS',','.join(x.bucket_id for x in CORNER_OPERATIONS_BUCKETS))
    rows=[source(i,selection='UNDER',odds=1.9,model_probability=.58,expected_value=.02,
                 expected_total_corners=9,line=9.5) for i in range(13)]
    s=build_snapshot(rows,NOW,'bucket_id='+b.bucket_id,now=NOW)
    assert len(s['operations_buckets'])==7
    assert s['operations_buckets'][1]['graded_n']==13
    assert s['operations_buckets'][1]['status']=='ACTIVE'
    assert s['filtered_count']==13
    html=render(s,'bucket_sort_table=operations-corner-buckets&bucket_sort=graded_n&bucket_dir=desc')
    assert html.index('id="operations-corner-buckets"') < html.index('Rolling and lifetime')
    assert 'operations-highlight' in html and 'selected-bucket' in html
    assert 'bucket_sort_table=buckets-multidimensional' in html
    assert 'bucket_dir=asc' in html and 'bucket_dir=desc' in html


def test_numeric_bucket_sort_both_directions_with_missing_last():
    rows=[{'roi_pct':2},{'roi_pct':None},{'roi_pct':15},{'roi_pct':-1}]
    assert [r['roi_pct'] for r in sorted_bucket_rows(rows,'roi_pct','asc')]==[-1,2,15,None]
    assert [r['roi_pct'] for r in sorted_bucket_rows(rows,'roi_pct','desc')]==[15,2,-1,None]


def test_table_sorts_and_filters_survive_other_table_sort_and_form_submission():
    from h2h.api.corner_analytics import table
    query = 'league=Spain&buckets-markets_sort=roi_pct&buckets-markets_dir=asc&bucket_sort_table=buckets-league&bucket_sort=graded_n&bucket_dir=desc'
    html = table('Markets', [{'roi_pct':10}, {'roi_pct':2}], (('roi_pct','ROI'),), table_id='buckets-markets',query=query)
    assert html.index('<td>2</td>') < html.index('<td>10</td>')
    assert 'league=Spain' in html
    full = render(build_snapshot([],NOW,now=NOW),query)
    assert 'name="buckets-markets_dir" value="asc"' in full
