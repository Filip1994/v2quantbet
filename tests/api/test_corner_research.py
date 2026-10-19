from datetime import UTC, datetime, timedelta

import pytest

from h2h.api.corner_analytics import analytics_tabs, build_snapshot, render
from h2h.cornerlab_entrypoint import configure_corner_only

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


def source(index=0, **changes):
    return dict({
        'shadow_bet_id': str(index), 'lab': 'CORNER', 'fixture_id': 'same-fixture',
        'market_key': 'TOTAL_CORNERS', 'selection': 'OVER', 'line': 9.5,
        'model_version': 'original-model', 'model_probability': .6, 'odds': 2,
        'market_probability': .5, 'expected_value': .2, 'edge': .1,
        'decision_at': NOW-timedelta(days=1), 'settled_at': NOW,
        'outcome': 'WIN', 'pnl_minor': 10000, 'stake_minor': 10000,
        'bookmaker_name': '1xBet', 'competition_name': 'League A', 'league_id': 1,
        'expected_total_corners': 10.2, 'cohort': 'HISTORICAL',
        'result_detail': {'actual_total_corners': 12, 'home_corner_kicks': 7, 'away_corner_kicks': 5},
    }, **changes)


def test_deduplicate_by_source_and_separate_football():
    rows = [source(), source(), source(1), source(2, lab='GOAL')]
    snap = build_snapshot(rows, NOW, now=NOW)
    assert snap['source_count'] == 2
    assert snap['windows']['lifetime']['flat_pnl_minor'] == 20000
    assert snap['disposition']['PLAYED']['signals'] == 0
    assert snap['execution_enabled'] is False
    assert snap['windows']['lifetime']['corner_mae'] == pytest.approx(1.8)


def test_only_rank_multidimensional_buckets_with_more_than_ten_graded():
    rows = [source(i) for i in range(10)] + [source(20, outcome='VOID', pnl_minor=0)]
    assert build_snapshot(rows, NOW, now=NOW)['cohorts']['multidimensional'] == []
    rows.append(source(11))
    bucket = build_snapshot(rows, NOW, now=NOW)['cohorts']['multidimensional'][0]
    assert bucket['graded_n'] == 11
    assert bucket['n'] == 12


def test_filters_pagination_and_sort_are_corner_specific():
    rows = [source(i, odds=1.8 + i / 100) for i in range(15)] + [source(99, cohort='FORWARD')]
    snap = build_snapshot(rows, NOW, 'cohort=HISTORICAL&sort=odds&dir=asc&page_size=5&page=2', now=NOW)
    assert snap['filtered_count'] == 15
    assert snap['page'] == 2 and len(snap['items']) == 5
    assert snap['items'][0]['shadow_bet_id'] == '5'
    assert snap['cohorts']['cohort'][0]['cohort'] == 'HISTORICAL'
    played = build_snapshot(rows, NOW, 'disposition=PLAYED', now=NOW)
    assert played['filtered_count'] == 0


def test_windows_stakes_drawdown_and_reversals_use_authoritative_source():
    rows = [source(0, decision_at=NOW-timedelta(days=8)),
            source(1, stake_minor=20000, pnl_minor=-20000, outcome='LOSS'),
            source(2, pnl_minor=None, outcome='PENDING', result_detail=None)]
    snap = build_snapshot(rows, NOW, now=NOW)
    lifetime = snap['windows']['lifetime']
    assert lifetime['flat_pnl_minor'] == -10000
    assert lifetime['roi_pct'] == pytest.approx(-100/3)
    assert lifetime['drawdown_minor'] == 20000
    assert snap['windows']['last_7d']['signals'] == 2
    assert snap['windows']['last_14d']['signals'] == 3
    assert snap['actual_corner_distributions']['home'] == {7: 2}


def test_page_contains_exactly_two_primary_tabs_and_escapes_provenance():
    snap = build_snapshot([source(home_team='<script>')], NOW, now=NOW)
    html = render(snap)
    assert 'Football Analytics' in html and 'Corner Analytics' in html
    assert '&lt;script&gt;' in html
    assert '<script>' not in html
    assert analytics_tabs('corner').count('<a ') == 2


def test_retired_execution_cannot_be_reenabled_by_inherited_variables(monkeypatch):
    for lab in ('GOAL', 'H2H', 'CARD'):
        monkeypatch.setenv(f'QUANTBET_QUANTLAB_{lab}_ENABLED', 'true')
    configure_corner_only()
    import os
    for lab in ('GOAL', 'H2H', 'CARD'):
        assert os.environ[f'QUANTBET_QUANTLAB_{lab}_ENABLED'] == 'false'


def test_existing_played_overlay_is_separate_and_uses_original_production_stakes():
    r = source(production_pick_id='existing', production_stake_minor=30000, production_odds=2.5)
    paper = build_snapshot([r], NOW, now=NOW)
    played = build_snapshot([r], NOW, 'disposition=PLAYED', now=NOW)
    assert paper['windows']['lifetime']['flat_pnl_minor'] == 10000
    assert played['windows']['lifetime']['flat_pnl_minor'] == 45000
    assert len(played['items']) == 1
    assert played['items'][0]['production_pick_id'] == 'existing'
    assert played['execution_enabled'] is False
