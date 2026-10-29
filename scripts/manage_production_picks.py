"""Audited production-only VOID or history reset. Default is a dry run.

PYTHONPATH=src python scripts/manage_production_picks.py void SHORT_ID ...
    --actor operator --reason 'User requested VOID' --request-id unique-request --apply
Use clear-history instead of void to archive the currently finished production picks.
Research data and operator PLAYED/SKIPPED decisions are never rewritten.
"""
from __future__ import annotations

import argparse
import os
from types import SimpleNamespace

import psycopg

from h2h.api.dashboard import DashboardService
from h2h.persistence.postgres_production_funnel import PostgreSQLProductionFunnelStateRepository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('void', 'clear-history'))
    parser.add_argument('pick_ids', nargs='*')
    parser.add_argument('--actor', required=True)
    parser.add_argument('--reason', required=True)
    parser.add_argument('--request-id', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if any(not value.strip() for value in (args.actor, args.reason, args.request_id)):
        parser.error('actor, reason and request-id must be nonblank')
    url = os.environ.get('DATABASE_PUBLIC_URL') or os.environ.get('DATABASE_URL')
    if not url:
        parser.error('DATABASE_PUBLIC_URL or DATABASE_URL is required')
    repo = PostgreSQLProductionFunnelStateRepository(url)
    if args.action == 'void':
        if not args.pick_ids:
            parser.error('void requires at least one pick id')
        targets = list(dict.fromkeys(
            value if value.startswith('production-pick-v1:')
            else repo.resolve_short_pick_id(value) for value in args.pick_ids
        ))
    else:
        if args.pick_ids:
            parser.error('clear-history does not accept pick ids')
        application = SimpleNamespace(runtime=SimpleNamespace(connect=lambda: psycopg.connect(url)))
        targets = [p['pick_id'] for p in DashboardService(application)._picks()
                   if DashboardService._is_history_pick(p)]
    with psycopg.connect(url) as connection, connection.cursor() as cursor:
        if args.apply and args.action == 'clear-history':
            cursor.execute('INSERT INTO production_funnel_history_resets '
                           '(request_id,actor,reason) VALUES (%s,%s,%s) '
                           'ON CONFLICT DO NOTHING RETURNING request_id',
                           (args.request_id, args.actor, args.reason))
            if cursor.fetchone() is None:
                cursor.execute('SELECT actor,reason FROM production_funnel_history_resets '
                               'WHERE request_id=%s', (args.request_id,))
                if cursor.fetchone() != (args.actor, args.reason):
                    raise ValueError('request-id conflicts with an earlier history reset')
                print('History reset already applied; no new picks archived')
                return
        for pick_id in sorted(targets):
            cursor.execute('SELECT home_team, away_team FROM production_funnel_picks '
                           'WHERE pick_id=%s FOR UPDATE', (pick_id,))
            row = cursor.fetchone()
            if row is None:
                raise LookupError(f'Production pick not found: {pick_id}')
            print(f'{args.action}: {pick_id} {row[0]} - {row[1]} apply={args.apply}')
            if args.apply and args.action == 'void':
                cursor.execute('SELECT production_void_pick(%s,%s,%s,%s)',
                               (pick_id, args.request_id + ':' + pick_id, args.actor, args.reason))
            elif args.apply:
                cursor.execute('INSERT INTO production_funnel_archives '
                               '(pick_id,request_id,actor,reason) VALUES (%s,%s,%s,%s) '
                               'ON CONFLICT (pick_id) DO NOTHING',
                               (pick_id, args.request_id, args.actor, args.reason))
        if not args.apply:
            connection.rollback()
    print(f'{len(targets)} production picks; {"committed" if args.apply else "dry run"}')


if __name__ == '__main__':
    main()
