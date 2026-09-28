-- Preserve the pre-PENDING operator semantics for picks that already existed
-- when the new explicit PENDING workflow was introduced.
--
-- Existing picks with an explicit operator event are left untouched.
-- Picks without any operator event are backfilled once as PLAYED.
-- Future registered picks receive no event and therefore derive PENDING.

INSERT INTO pick_operator_state_events (
    event_id,
    pick_id,
    state,
    occurred_at,
    request_id
)
SELECT
    'pick-operator-state-event-v1:'
        || md5('legacy-played-backfill-v1:' || r.pick_id)
        || md5('legacy-played-backfill-v1:' || r.pick_id || ':tail'),
    r.pick_id,
    'PLAYED',
    r.registered_at,
    'legacy-played-backfill-v1:' || r.pick_id
FROM registered_picks r
WHERE NOT EXISTS (
    SELECT 1
    FROM pick_operator_state_events e
    WHERE e.pick_id = r.pick_id
)
ON CONFLICT DO NOTHING;
