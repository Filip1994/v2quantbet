-- Switch currently unresolved Production picks into research-only SKIPPED state.
--
-- Future Production registrations are auto-skipped atomically by the registration
-- repository. This one-time backfill releases any exposure held by picks that were
-- already open when that behavior was enabled. Settled historical picks are untouched.

WITH unresolved_reserved AS (
    SELECT l.pick_id
    FROM bankroll_ledger_entries l
    WHERE l.entry_type = 'STAKE_RESERVED'
      AND NOT EXISTS (
          SELECT 1
          FROM pick_settlement_events e
          WHERE e.pick_id = l.pick_id
            AND e.outcome IS NOT NULL
            AND NOT EXISTS (
                SELECT 1
                FROM pick_settlement_events successor
                WHERE successor.prior_event_id = e.settlement_event_id
            )
      )
),
latest_operator AS (
    SELECT DISTINCT ON (e.pick_id)
        e.pick_id,
        e.state
    FROM pick_operator_state_events e
    JOIN unresolved_reserved r ON r.pick_id = e.pick_id
    ORDER BY e.pick_id, e.occurred_at DESC, e.persisted_at DESC, e.event_id DESC
)
INSERT INTO pick_operator_state_events (
    event_id,
    pick_id,
    state,
    occurred_at,
    request_id
)
SELECT
    'pick-operator-state-event-v1:'
        || md5('production-auto-skip-backfill-v1:' || p.pick_id)
        || md5('production-auto-skip-backfill-v1:' || p.pick_id || ':tail'),
    p.pick_id,
    'SKIPPED',
    CURRENT_TIMESTAMP,
    'production-auto-skip-backfill-v1:' || p.pick_id
FROM registered_picks p
JOIN unresolved_reserved r ON r.pick_id = p.pick_id
LEFT JOIN latest_operator o ON o.pick_id = p.pick_id
WHERE COALESCE(o.state, 'PENDING') <> 'SKIPPED'
ON CONFLICT DO NOTHING;
