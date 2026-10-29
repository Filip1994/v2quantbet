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


def test_last_10_20_30_are_settlement_ordered_and_1xbet_only(monkeypatch):
    from datetime import timedelta

    b = CORNER_OPERATIONS_BUCKETS[1]  # UNDER 1.75-2.00
    monkeypatch.setenv('QUANTBET_PRODUCTION_INTAKE_BUCKETS', b.bucket_id)
    rows = []
    for i in range(35):
        loss = i < 3 or i in {12, 13}
        one_xbet = i < 12
        rows.append(source(
            i, selection='UNDER', odds=1.9, model_probability=.58,
            expected_value=.02, expected_total_corners=9, line=9.5,
            bookmaker_id=11 if one_xbet else 8,
            bookmaker_name='1xBet' if one_xbet else 'bet365',
            settled_at=NOW-timedelta(minutes=i),
            decision_at=NOW-timedelta(days=1, minutes=i),
            outcome='LOSS' if loss else 'WIN',
            pnl_minor=-10000 if loss else 9000,
        ))
    # A more recently VOIDed pick must not displace any graded slot.
    rows.append(source(
        99, selection='UNDER', odds=1.9, model_probability=.58,
        expected_value=.02, expected_total_corners=9, line=9.5,
        bookmaker_id=11, bookmaker_name='1xBet',
        settled_at=NOW+timedelta(minutes=1), outcome='VOID', pnl_minor=0,
    ))
    snap = build_snapshot(rows, NOW, now=NOW)
    one = snap['operations_tracking']['1xbet'][b.bucket_id]
    all_bookies = snap['operations_tracking']['all'][b.bucket_id]

    assert one['last_10']['graded_n'] == 10
    assert one['last_10']['wins'] == 7
    assert one['last_10']['losses'] == 3
    assert one['last_10']['roi_pct'] == 33.0
    assert one['last_10']['win_rate_pct'] == 70.0
    assert one['last_10']['complete'] is True
    assert one['last_20']['graded_n'] == 12
    assert one['last_20']['window_label'] == '12/20'
    assert one['last_20']['complete'] is False
    assert one['last_30']['window_label'] == '12/30'
    assert one['lifetime']['graded_n'] == 12
    assert all_bookies['last_30']['graded_n'] == 30
    assert all_bookies['lifetime']['graded_n'] == 35

    html = render(snap)
    assert 'Last 10 graded · 1xBet PAPER' in html
    assert 'Last 20 graded · 1xBet PAPER' in html
    assert 'Last 30 graded · 1xBet PAPER' in html
    assert 'tracking_scope=all' in html
    assert '12/20' in html


def test_only_configured_buckets_are_blue_and_other_two_are_off(monkeypatch):
    from h2h.api.corner_analytics import table

    selected = (
        CORNER_OPERATIONS_BUCKETS[0], CORNER_OPERATIONS_BUCKETS[1],
        CORNER_OPERATIONS_BUCKETS[3], CORNER_OPERATIONS_BUCKETS[4],
        CORNER_OPERATIONS_BUCKETS[5],
    )
    monkeypatch.setenv(
        'QUANTBET_PRODUCTION_INTAKE_BUCKETS',
        ','.join(b.bucket_id for b in selected),
    )
    rows = []
    for idx, bucket in enumerate(CORNER_OPERATIONS_BUCKETS):
        odds = sum(float(x) for x in bucket.odds) / 2
        prob = sum(float(x) for x in bucket.probability) / 2
        ev = sum(float(x) for x in bucket.ev) / 2
        gap = sum(float(x) for x in bucket.gap) / 2
        for i in range(13):
            rows.append(source(
                idx * 100 + i, selection=bucket.selection, odds=odds,
                model_probability=prob, expected_value=ev,
                line=9.5, expected_total_corners=9.5 + gap,
                bookmaker_id=11, bookmaker_name='1xBet',
            ))
    snap = build_snapshot(rows, NOW, now=NOW)
    statuses = {r['bucket_id']: r['status'] for r in snap['operations_buckets']}
    assert sum(s == 'ACTIVE' for s in statuses.values()) == 5
    assert sum(s == 'OFF' for s in statuses.values()) == 2

    html = table(
        'Operations', snap['operations_buckets'],
        (('selection', 'Market'), ('status', 'Operations')),
        table_id='operations-corner-buckets', highlighted=True,
    )
    assert html.count('class="selected-bucket"') == 5
    assert html.count('<td>OFF</td>') == 2


def test_missing_research_allowlist_does_not_claim_all_seven_active(monkeypatch):
    monkeypatch.delenv('QUANTBET_PRODUCTION_INTAKE_BUCKETS', raising=False)
    snap = build_snapshot([], NOW, now=NOW)
    assert snap['operations_allowlist_verified'] is False
    assert all(b['status'] == 'OFF' for b in snap['operations_buckets'])
    assert 'active highlighting is unavailable' in render(snap)
