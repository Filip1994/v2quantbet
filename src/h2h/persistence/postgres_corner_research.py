"""Research adapter over CornerLab's authoritative paper ledger (no money writes)."""
from __future__ import annotations

from typing import Any

from h2h.quantlab.repository import PostgreSQLQuantLabRepository


class PostgreSQLCornerResearchRepository:
    def __init__(self, database_url: str):
        self._database_url = database_url
        self._source = PostgreSQLQuantLabRepository(database_url)

    def snapshot(self) -> tuple[Any, tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
        # Use one repeatable snapshot for registry, features and latest event. The
        # source query resolves correction/reversal events once per source pick.
        import psycopg
        from contextlib import nullcontext

        with psycopg.connect(self._database_url, options='-c statement_timeout=30000') as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            activation = connection.execute(
                'SELECT activated_at FROM research_corner_activation WHERE singleton'
            ).fetchone()[0]
            registry = {
                row[0]: {'cohort': row[1], 'ingested_at': row[2], 'disposition': row[3],
                         'strategy_version': row[4], 'execution_enabled': False}
                for row in connection.execute(
                    'SELECT source_shadow_bet_id,cohort,ingested_at,disposition,strategy_version '
                    'FROM research_corner_signals'
                )
            }
            source = PostgreSQLQuantLabRepository(connect=lambda: nullcontext(connection))
            rows = source.list_all_bets('CORNER')
            played = {
                r[0]: {'production_pick_id': r[1], 'production_stake_minor': r[2],
                       'production_odds': r[3], 'production_played_at': r[4]}
                for r in connection.execute('''
                    SELECT p.source_pick_id,p.pick_id,p.stake_minor,p.odds,s.occurred_at
                    FROM production_funnel_picks p
                    JOIN LATERAL (
                        SELECT state,occurred_at FROM production_funnel_state_events s
                        WHERE s.pick_id=p.pick_id
                        ORDER BY occurred_at DESC,persisted_at DESC,event_id DESC LIMIT 1
                    ) s ON s.state='PLAYED'
                    WHERE p.source_universe='CORNERLAB'
                ''')
            }
            # Bound the odds explorer by fixture and index, never scan the full
            # historical odds table on a Research request. Archived history stays
            # in the original tables/object archive and is not deleted.
            fixtures = list(dict.fromkeys(r['fixture_id'] for r in rows))[:40]
            cursor = connection.execute('''
                SELECT DISTINCT ON (fixture_id,bookmaker_id,provider_bet_id,raw_selection)
                    fixture_id,bookmaker_id,bookmaker_name,provider_bet_id,provider_bet_name,
                    raw_selection,parsed_line,odds,captured_at,market_observation_id
                FROM unnest(%s::text[]) f(id)
                CROSS JOIN LATERAL (
                    SELECT * FROM quantlab_market_observations m
                    WHERE m.fixture_id=f.id AND m.lab_owner='CORNER'
                    ORDER BY m.captured_at DESC LIMIT 800
                ) quotes
                ORDER BY fixture_id,bookmaker_id,provider_bet_id,raw_selection,captured_at DESC,market_observation_id DESC
            ''', (fixtures,))
            names = [c.name for c in cursor.description]
            observations = tuple(dict(zip(names,r)) for r in cursor.fetchall())
            return activation, tuple(
                {**row, **registry[row['shadow_bet_id']], **played.get(row['shadow_bet_id'], {})} for row in rows
                if row['shadow_bet_id'] in registry
            ), observations
