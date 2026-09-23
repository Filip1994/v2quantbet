-- QuantBet issue #15 — append-only operator PLAYED/SKIPPED overrides.

CREATE TABLE pick_operator_state_events (
    event_id TEXT PRIMARY KEY
        CHECK (event_id ~ '^pick-operator-state-event-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('PLAYED', 'SKIPPED')),
    occurred_at TIMESTAMPTZ NOT NULL,
    request_id TEXT NOT NULL UNIQUE CHECK (length(trim(request_id)) > 0),
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (event_id, pick_id)
);

CREATE INDEX idx_pick_operator_state_history
    ON pick_operator_state_events (pick_id, occurred_at DESC, persisted_at DESC, event_id DESC);

CREATE FUNCTION reject_pick_operator_state_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'pick operator state history is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pick_operator_state_events_append_only
    BEFORE UPDATE OR DELETE ON pick_operator_state_events
    FOR EACH ROW EXECUTE FUNCTION reject_pick_operator_state_mutation();
