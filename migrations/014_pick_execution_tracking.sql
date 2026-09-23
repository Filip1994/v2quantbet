-- QuantBet operator execution tracking.
-- This layer records whether the human operator actually placed a registered system pick.
-- It is intentionally separate from immutable system registration and simulated bankroll accounting.

CREATE TABLE pick_execution_events (
    execution_event_id TEXT PRIMARY KEY
        CHECK (execution_event_id ~ '^pick-execution-event-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    execution_status TEXT NOT NULL CHECK (execution_status IN ('PLAYED', 'SKIPPED')),
    actual_stake_minor BIGINT CHECK (actual_stake_minor > 0),
    actual_odd_decimal NUMERIC CHECK (actual_odd_decimal > 1),
    bookmaker TEXT CHECK (bookmaker IS NULL OR length(trim(bookmaker)) > 0),
    reason_code TEXT CHECK (
        reason_code IS NULL
        OR reason_code IN ('BOOKMAKER_LIMIT', 'PRICE_MOVED', 'NOT_PLACED', 'OTHER')
    ),
    note TEXT,
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    request_id TEXT NOT NULL UNIQUE CHECK (length(trim(request_id)) > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    CHECK (
        execution_status = 'PLAYED'
        OR (
            execution_status = 'SKIPPED'
            AND actual_stake_minor IS NULL
            AND actual_odd_decimal IS NULL
        )
    )
);

CREATE INDEX idx_pick_execution_history
    ON pick_execution_events (pick_id, occurred_at DESC, execution_event_id DESC);

CREATE INDEX idx_pick_execution_status
    ON pick_execution_events (execution_status, occurred_at DESC, execution_event_id DESC);

CREATE FUNCTION reject_pick_execution_fact_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'pick execution events are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pick_execution_events_append_only
    BEFORE UPDATE OR DELETE ON pick_execution_events
    FOR EACH ROW EXECUTE FUNCTION reject_pick_execution_fact_mutation();
