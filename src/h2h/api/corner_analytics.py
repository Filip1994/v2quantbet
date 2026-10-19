"""Corner Research analytics over immutable source IDs; never posts financial entries."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from math import exp, factorial
from statistics import mean
from typing import Any
from urllib.parse import parse_qs, urlencode

from h2h.api.research_analytics import cohort_metrics

PATH = '/research/analytics/corners'


def analytics_tabs(active: str) -> str:
    return '<nav aria-label="Analytics tabs" class="analytics-tabs">' + ''.join(
        f'<a href="{path}" aria-current="{"page" if key == active else "false"}">{title}</a> '
        for key, path, title in (
            ('football', '/research/analytics', 'Football Analytics'),
            ('corner', PATH, 'Corner Analytics'),
        )
    ) + '</nav>'


def number(value: Any) -> float | None:
    return None if value is None else float(value)


def band(value: Any, width: float) -> str:
    if value is None:
        return 'UNRECORDED'
    low = (float(value) // width) * width
    return f'{low:g}–{low + width:g}'


def derive(row: dict[str, Any]) -> dict[str, Any]:
    r = dict(row)
    detail = r.get('result_detail') or {}
    payload = r.get('corner_feature_payload') or {}
    raw = payload.get('raw_features', {})
    expected, line = number(r.get('expected_total_corners')), number(r.get('line'))
    r.update(
        source='CORNERLAB', market=r['market_key'], bookmaker=r.get('bookmaker_name'),
        qualified_at=r['decision_at'], model_version_id=r['model_version'],
        market_fair_probability=r.get('market_probability'),
        policy_config_fingerprint=r.get('policy_version'),
        actual_home_corners=detail.get('home_corner_kicks'),
        actual_away_corners=detail.get('away_corner_kicks'),
        actual_total_corners=detail.get('actual_total_corners'),
        line_gap=None if expected is None or line is None else expected - line,
        home_corners_for=raw.get('home_l5_corners_for'),
        away_corners_for=raw.get('away_l5_corners_for'),
        clv_ppm=None,
    )
    r['probability_bucket'] = band(r.get('model_probability'), .05)
    r['ev_bucket'] = band(r.get('expected_value'), .05)
    r['odds_bucket'] = band(r.get('odds'), .25)
    r['line_gap_bucket'] = band(r['line_gap'], 1)
    r['edge_bucket'] = band(r.get('edge'), .05)
    # Source shadow records are paper picks. A fixture's production PLAYED state
    # cannot turn a different corner-market selection into a played position.
    r['disposition'] = 'PAPER'
    r['execution_enabled'] = False
    return r


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # The shared strategy framework supplies evidence bands and calibration.
    # Its flat-stake denominator is replaced with the preserved source stakes.
    safe = [{**r, 'pnl_minor': round(int(r.get('pnl_minor') or 0) * 10000 / int(r['stake_minor'])),
             'market_fair_probability': r.get('market_fair_probability') or 1 / float(r['odds'])}
            for r in rows]
    m = cohort_metrics(safe, fixed_stake_minor=10000)
    settled = [r for r in rows if r.get('outcome') in {'WIN', 'LOSS', 'VOID'}]
    graded = [r for r in settled if r['outcome'] in {'WIN', 'LOSS'}]
    m['flat_pnl_minor'] = sum(int(r.get('pnl_minor') or 0) for r in settled)
    stake = sum(int(r['stake_minor']) for r in graded)
    m['roi_pct'] = 100 * m['flat_pnl_minor'] / stake if stake else None
    m['stake_minor'] = stake
    m['signals'] = len(rows)
    m['pending_n'] = len(rows) - len(settled)
    cumulative = peak = drawdown = 0
    curve = []
    for r in sorted(settled, key=lambda r: (r.get('settled_at') or r['decision_at'], r['shadow_bet_id'])):
        cumulative += int(r.get('pnl_minor') or 0)
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
        curve.append({'at': r.get('settled_at') or r['decision_at'], 'source_id': r['shadow_bet_id'],
                      'pnl_minor': int(r.get('pnl_minor') or 0), 'cumulative_pnl_minor': cumulative})
    m['drawdown_minor'] = drawdown
    m['cumulative_pnl'] = curve
    errors = [float(r['actual_total_corners']) - float(r['expected_total_corners'])
              for r in settled if r.get('actual_total_corners') is not None
              and r.get('expected_total_corners') is not None]
    m['expected_actual_n'] = len(errors)
    m['corner_bias'] = mean(errors) if errors else None
    m['corner_mae'] = mean(abs(e) for e in errors) if errors else None
    return m


def groups(rows: list[dict[str, Any]], dimensions: tuple[str, ...], *, ranked=False) -> list[dict[str, Any]]:
    buckets = defaultdict(list)
    for r in rows:
        buckets[tuple(str(r.get(d) if r.get(d) is not None else 'UNRECORDED') for d in dimensions)].append(r)
    result = [{**dict(zip(dimensions, key)), **metrics(items)} for key, items in buckets.items()]
    if ranked:
        result = [r for r in result if r['graded_n'] > 10]
        result.sort(key=lambda r: (r['roi_pct'] if r['roi_pct'] is not None else -float('inf'), r['graded_n']), reverse=True)
    else:
        result.sort(key=lambda r: tuple(str(r[d]) for d in dimensions))
    for r in result:
        r.pop('cumulative_pnl')
    return result


def filter_rows(rows: list[dict[str, Any]], params: dict[str, list[str]]) -> list[dict[str, Any]]:
    exact = {'market': 'market', 'selection': 'selection', 'cohort': 'cohort',
             'disposition': 'disposition', 'outcome': 'outcome', 'model_version': 'model_version_id'}
    for param, field in exact.items():
        value = params.get(param, [''])[0].strip()
        if value:
            rows = [r for r in rows if str(r.get(field, '')).casefold() == value.casefold()]
    for param, field in (('league', 'competition_name'), ('bookmaker', 'bookmaker')):
        value = params.get(param, [''])[0].strip().casefold()
        if value:
            rows = [r for r in rows if value in str(r.get(field, '')).casefold()]
    for param, field in (('p', 'model_probability'), ('ev', 'expected_value'), ('odds', 'odds'), ('gap', 'line_gap')):
        for suffix, minimum in (('min', True), ('max', False)):
            raw = params.get(f'{param}_{suffix}', [''])[0].strip()
            if raw:
                threshold = float(raw)
                rows = [r for r in rows if r.get(field) is not None and
                        (float(r[field]) >= threshold if minimum else float(r[field]) <= threshold)]
    for param, minimum in (('from', True), ('to', False)):
        raw = params.get(param, [''])[0].strip()
        if raw:
            threshold = datetime.fromisoformat(raw).replace(tzinfo=UTC)
            if not minimum:
                threshold += timedelta(days=1)
            rows = [r for r in rows if (r['decision_at'] >= threshold if minimum else r['decision_at'] < threshold)]
    return rows


def build_snapshot(source_rows, activation, query='', *, now=None, observations=()) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    # Source ID deduplication only: separate selections/lines must never be
    # collapsed just because the fixture also has a football research pick.
    unique = {r['shadow_bet_id']: derive(r) for r in source_rows if r.get('lab') == 'CORNER'}
    params = parse_qs(query, keep_blank_values=True)
    paper = list(unique.values())
    played = []
    for r in paper:
        if not r.get('production_pick_id'):
            continue
        stake = int(r['production_stake_minor'])
        odds = Decimal(str(r['production_odds']))
        outcome = r['outcome']
        pnl = (int((Decimal(stake)*(odds-1)).quantize(Decimal(1),rounding=ROUND_HALF_UP)) if outcome=='WIN'
               else -stake if outcome=='LOSS' else 0 if outcome=='VOID' else None)
        played.append({**r, 'disposition':'PLAYED', 'stake_minor':stake, 'odds':odds,
                       'pnl_minor':pnl, 'source_paper_pnl_minor':r.get('pnl_minor')})
    selected_disposition = params.get('disposition',['PAPER'])[0] or 'PAPER'
    selected_params = {**params, 'disposition':[selected_disposition]}
    rows = filter_rows(played if selected_disposition == 'PLAYED' else paper, selected_params)
    windows = {'lifetime': metrics(rows)}
    for days in (7, 14, 30):
        windows[f'last_{days}d'] = metrics([r for r in rows if now - timedelta(days=days) <= r['decision_at'] <= now])
    dimensions = {
        'markets': ('market', 'selection'), 'league': ('competition_name', 'league_id'),
        'line_gap': ('market', 'selection', 'line_gap_bucket'),
        'calibration': ('probability_bucket',), 'model_ev': ('ev_bucket',),
        'bookmaker': ('bookmaker',), 'cohort': ('cohort',),
        'multidimensional': ('market', 'selection', 'odds_bucket', 'probability_bucket', 'ev_bucket', 'line_gap_bucket'),
        'league_multidimensional': ('competition_name', 'market', 'selection', 'line_gap_bucket'),
    }
    sort = params.get('sort', ['decision_at'])[0]
    allowed = {'decision_at', 'odds', 'model_probability', 'expected_value', 'pnl_minor', 'line_gap', 'competition_name'}
    if sort not in allowed:
        sort = 'decision_at'
    descending = params.get('dir', ['desc'])[0] != 'asc'
    rows.sort(key=lambda r: (r.get(sort) is not None, r.get(sort) if r.get(sort) is not None else 0, r['shadow_bet_id']), reverse=descending)
    size = max(1, min(200, int(params.get('page_size', ['50'])[0])))
    pages = max(1, (len(rows) + size - 1) // size)
    page = max(1, min(pages, int(params.get('page', ['1'])[0])))
    graded = [r for r in rows if r['outcome'] in {'WIN', 'LOSS'}]
    histograms = {side: dict(sorted(Counter(int(r[f'actual_{side}_corners']) for r in graded
                                          if r.get(f'actual_{side}_corners') is not None).items()))
                  for side in ('home', 'away')}
    lambdas = [float(r['expected_total_corners']) for r in rows if r.get('expected_total_corners') is not None]
    distribution = {str(k): mean(exp(-v) * v ** k / factorial(k) for v in lambdas) for k in range(31)} if lambdas else {}
    filtered_fixture_ids = {r['fixture_id'] for r in rows}
    quotes = [dict(q) for q in observations if q['fixture_id'] in filtered_fixture_ids]
    market_filter = params.get('market',[''])[0]
    if market_filter == 'CORNER_HANDICAP':
        # Handicap prices exist independently of the totals-only pick policy.
        fixture_ids = {r['fixture_id'] for r in filter_rows(list(unique.values()), {k:v for k,v in params.items() if k != 'market'})}
        quotes = [dict(q) for q in observations if q['fixture_id'] in fixture_ids
                  and ('handicap' in q['provider_bet_name'].casefold() or 'asian' in q['provider_bet_name'].casefold())]
    return {
        'contract_version': 'CORNER_RESEARCH_V1', 'activation_at': activation,
        'generated_at': now, 'source_count': len(unique), 'filtered_count': len(rows),
        'execution_enabled': False, 'selected_disposition': selected_disposition,
        'accounting': 'PAPER counterfactual source ledger and existing PLAYED production overlay are separate views. Never sum them. No bankroll entries.',
        'strategy_framework': 'Research cohort_metrics; PAPER evaluation only',
        'ranking_rule': 'graded_n > 10', 'windows': windows,
        'cohorts': {name: groups(rows, dims, ranked='multidimensional' in name)
                    for name, dims in dimensions.items()},
        'disposition': {value: metrics(filter_rows(dataset,{k:v for k,v in params.items() if k!='disposition'}))
                        for value,dataset in (('PLAYED',played),('PAPER',paper))},
        'actual_corner_distributions': histograms, 'model_total_poisson_distribution': distribution,
        'capabilities': {'TOTAL_CORNERS': 'Original half-line model and settlement',
                         'CORNER_HANDICAP': 'No graded model signals in original CornerLab; never fabricated'},
        'page': page, 'pages': pages, 'page_size': size, 'sort': sort,
        'observed_corner_prices': quotes[:1000],
        'observed_price_scope': 'Latest bounded stored series from 40 recent CornerLab fixtures; no new API requests',
        'items': rows[(page - 1) * size:page * size],
    }


def fmt(value):
    if value is None:
        return '—'
    if isinstance(value, float):
        return f'{value:.3f}'
    return str(value)


def table(title, rows, fields):
    def cell(row,key):
        value=row.get(key)
        if key in {'flat_pnl_minor','pnl_minor','drawdown_minor','cumulative_pnl_minor'} and value is not None:
            return f'{float(value)/100:,.2f}'
        return fmt(value)
    headers = ''.join(f'<th>{escape(label)}</th>' for _, label in fields)
    body = ''.join('<tr>' + ''.join(f'<td>{escape(cell(r,key))}</td>' for key, _ in fields) + '</tr>' for r in rows)
    return f'<section><h2>{escape(title)}</h2><div class="scroll"><table><thead><tr>{headers}</tr></thead><tbody>{body or "<tr><td>No matching data</td></tr>"}</tbody></table></div></section>'


def render(snapshot, query='') -> str:
    params = parse_qs(query, keep_blank_values=True)
    def link(**changes):
        p = {k: v[0] for k, v in params.items()}; p.update(changes)
        return PATH + '?' + urlencode(p)
    inputs = ''.join(f'<label>{escape(label)}<input name="{key}" value="{escape(params.get(key,[""])[0], quote=True)}"></label>'
                     for key, label in (('league','League'), ('bookmaker','Bookmaker'), ('model_version','Model version'),
                                        ('from','From date'), ('to','To date'), ('p_min','Min model P (0–1)'), ('p_max','Max model P'),
                                        ('ev_min','Min EV'), ('ev_max','Max EV'), ('odds_min','Min odds'), ('odds_max','Max odds'),
                                        ('gap_min','Min line gap'), ('gap_max','Max line gap')))
    for key, label, values in (
        ('market','Market',('TOTAL_CORNERS','CORNER_HANDICAP','HOME_CORNERS','AWAY_CORNERS')),
        ('selection','Selection',('OVER','UNDER','HOME','AWAY')),
        ('cohort','Cohort',('HISTORICAL','FORWARD')), ('disposition','Positions',('PAPER','PLAYED')),
        ('outcome','Result',('PENDING','WIN','LOSS','VOID')),
        ('sort','Sort',('decision_at','odds','model_probability','expected_value','pnl_minor','line_gap','competition_name')),
        ('dir','Direction',('desc','asc')),
    ):
        options = '<option value="">All</option>' if key not in {'sort','dir','disposition'} else ''
        options += ''.join(f'<option {"selected" if params.get(key,["PAPER" if key=="disposition" else ""])[0] == v else ""}>{v}</option>' for v in values)
        inputs += f'<label>{label}<select name="{key}">{options}</select></label>'
    overview = table('Rolling and lifetime ' + snapshot['selected_disposition'] + ' performance', [{'window': k, **v} for k,v in snapshot['windows'].items()],
                     (('window','Window'),('signals','Signals'),('graded_n','Graded N'),('wins','W'),('losses','L'),('voids','V'),
                      ('flat_pnl_minor','PnL RSD'),('roi_pct','ROI %'),('drawdown_minor','Drawdown RSD'),('corner_bias','Actual − expected'),('corner_mae','MAE')))
    common = (('graded_n','Graded N'),('wins','W'),('losses','L'),('roi_pct','ROI %'),('flat_pnl_minor','PnL RSD'),
              ('avg_model_probability_pct','Model P %'),('avg_ev_pct','EV %'),('calibration_gap_pp','Calibration pp'))
    body = ''
    for key, fields in (
        ('markets',(('market','Market'),('selection','Selection'))),
        ('league',(('competition_name','League'),('league_id','ID'))),
        ('line_gap',(('market','Market'),('selection','Selection'),('line_gap_bucket','Expected − line'))),
        ('calibration',(('probability_bucket','Model P'),)), ('model_ev',(('ev_bucket','EV'),)),
        ('bookmaker',(('bookmaker','Bookmaker'),)), ('cohort',(('cohort','Cohort'),)),
        ('multidimensional',(('market','Market'),('selection','Selection'),('odds_bucket','Odds'),('probability_bucket','P'),('ev_bucket','EV'),('line_gap_bucket','Gap'))),
        ('league_multidimensional',(('competition_name','League'),('market','Market'),('selection','Selection'),('line_gap_bucket','Gap'))),
    ):
        body += table(key.replace('_',' ').title() + (' · ranked only with graded N > 10' if 'multidimensional' in key else ''), snapshot['cohorts'][key], fields + common)
    items = table('Signal history and provenance', snapshot['items'], (
        ('decision_at','Decision UTC'),('home_team','Home'),('away_team','Away'),('market','Market'),('selection','Selection'),('line','Line'),
        ('expected_total_corners','Expected'),('actual_total_corners','Actual'),('actual_home_corners','Home corners'),('actual_away_corners','Away corners'),
        ('line_gap','Line gap'),('home_corners_for','Home L5 corners'),('away_corners_for','Away L5 corners'),
        ('bookmaker','Bookmaker'),('odds','Odds'),('model_probability','Model P'),('expected_value','EV'),('outcome','Outcome'),('pnl_minor','PAPER PnL RSD'),
        ('cohort','Cohort'),('disposition','Position'),('model_version','Model'),('shadow_bet_id','Source ID')))
    curve = table('Cumulative ' + snapshot['selected_disposition'] + ' PnL', snapshot['windows']['lifetime']['cumulative_pnl'],
                  (('at','Settled UTC'),('pnl_minor','Change RSD'),('cumulative_pnl_minor','Cumulative RSD'),('source_id','Source ID')))
    distributions = ''.join(table(f'Actual {side} corner distribution', [{'corners': k,'count':v} for k,v in counts.items()], (('corners','Corners'),('count','Count')))
                            for side,counts in snapshot['actual_corner_distributions'].items())
    distributions += table('Model total corner distribution · mixture of preserved Poisson projections',
                           [{'corners': k, 'p': v} for k,v in snapshot['model_total_poisson_distribution'].items()], (('corners','Total'),('p','Probability')))
    prices = table('Corner totals, team totals and handicap bookmaker prices · stored observations', snapshot['observed_corner_prices'],
                   (('fixture_id','Fixture'),('provider_bet_name','Market'),('raw_selection','Selection'),('parsed_line','Line'),('bookmaker_name','Bookmaker'),('odds','Odds'),('captured_at','Captured UTC'),('market_observation_id','Provenance')))
    separation = table('PLAYED / PAPER separation', [{'position':k,**v} for k,v in snapshot['disposition'].items()],
                       (('position','Position'),('signals','Signals'),('graded_n','Graded N'),('flat_pnl_minor','PnL RSD')))
    nav = f'<p>Page {snapshot["page"]} / {snapshot["pages"]} · {snapshot["filtered_count"]} signals · <a href="{escape(link(page=max(1,snapshot["page"]-1)),quote=True)}">Previous</a> · <a href="{escape(link(page=min(snapshot["pages"],snapshot["page"]+1)),quote=True)}">Next</a></p>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Corner Analytics · Research</title>
<style>body{{font:14px system-ui;background:#0d1117;color:#dbe5ee;margin:0}}main{{max-width:1600px;margin:auto;padding:24px}}a{{color:#9ecbff}}.analytics-tabs{{display:flex;gap:20px;padding:20px 0}}[aria-current=page]{{font-weight:bold;color:#7ee7b5}}form{{display:flex;flex-wrap:wrap;gap:10px}}label{{display:grid;font-size:12px;gap:4px}}input,select,button{{background:#172331;color:#eef;border:1px solid #42536a;padding:8px;border-radius:5px}}section{{margin:24px 0;border:1px solid #26394c;padding:14px;border-radius:9px}}h2{{font-size:17px}}.scroll{{overflow:auto;max-height:600px}}table{{border-collapse:collapse;width:100%;white-space:nowrap;font-size:12px}}th,td{{padding:9px;border-bottom:1px solid #26394c;text-align:left}}th{{position:sticky;top:0;background:#172331}}.note{{color:#aac0d2;line-height:1.7}}</style></head><body><main>
<header><a href="https://quantbet-dashboard-production.up.railway.app/hub">🏠 HUB</a> · <a href="/research">Research Board</a><h1>Research Analytics</h1></header>{analytics_tabs('corner')}
<p class="note">CornerLab → Research → <a href="https://quantbet-kellylab-production.up.railway.app">KellyLab</a> review. New signals remain PAPER; execution disabled. Existing PLAYED positions are a separate read-only production overlay using frozen stakes and prices. PAPER and PLAYED totals must never be added together. Forward activation: {escape(str(snapshot['activation_at']))}. Historical cohorts keep original decision times. PnL uses one latest authoritative settlement per source ID; no bankroll postings. Model P/EV remain original. Corner handicaps have no graded model signals in the preserved model; unsupported projections remain unavailable.</p>
<form method="get">{inputs}<button>Apply corner filters</button><a href="{PATH}">Clear corner filters</a></form>
{overview}{separation}{body}{nav}{items}{nav}{prices}{distributions}{curve}
<p><a href="{PATH}.json?{escape(query,quote=True)}">Filtered JSON and complete cohort evidence</a></p></main></body></html>'''
