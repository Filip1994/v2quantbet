-- Production-only overrides. Source picks, observations and research remain immutable.
CREATE TABLE production_funnel_voids (
    pick_id TEXT PRIMARY KEY REFERENCES production_funnel_picks(pick_id),
    request_id TEXT NOT NULL UNIQUE CHECK (length(trim(request_id)) > 0),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE production_funnel_history_resets (
    request_id TEXT PRIMARY KEY CHECK (length(trim(request_id)) > 0),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE production_funnel_archives (
    pick_id TEXT PRIMARY KEY REFERENCES production_funnel_picks(pick_id),
    request_id TEXT NOT NULL REFERENCES production_funnel_history_resets(request_id),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER production_funnel_voids_append_only
    BEFORE UPDATE OR DELETE ON production_funnel_voids
    FOR EACH ROW EXECUTE FUNCTION reject_production_funnel_fact_mutation();
CREATE TRIGGER production_funnel_archives_append_only
    BEFORE UPDATE OR DELETE ON production_funnel_archives
    FOR EACH ROW EXECUTE FUNCTION reject_production_funnel_fact_mutation();
CREATE TRIGGER production_funnel_history_resets_append_only
    BEFORE UPDATE OR DELETE ON production_funnel_history_resets
    FOR EACH ROW EXECUTE FUNCTION reject_production_funnel_fact_mutation();

CREATE FUNCTION production_void_pick(
    target_pick_id TEXT, action_request_id TEXT, action_actor TEXT, action_reason TEXT
) RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE previous production_funnel_voids%ROWTYPE;
BEGIN
    IF NULLIF(trim(action_request_id), '') IS NULL
       OR NULLIF(trim(action_actor), '') IS NULL
       OR NULLIF(trim(action_reason), '') IS NULL THEN
        RAISE EXCEPTION 'request_id, actor and reason are required';
    END IF;
    PERFORM 1 FROM production_funnel_picks WHERE pick_id = target_pick_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Production pick not found: %', target_pick_id; END IF;
    SELECT * INTO previous FROM production_funnel_voids WHERE pick_id = target_pick_id;
    IF FOUND THEN
        IF previous.request_id = action_request_id AND previous.actor = action_actor
           AND previous.reason = action_reason THEN RETURN target_pick_id; END IF;
        RAISE EXCEPTION 'Production pick already voided with another action';
    END IF;
    INSERT INTO production_funnel_voids(pick_id, request_id, actor, reason)
        VALUES (target_pick_id, action_request_id, action_actor, action_reason);
    RETURN target_pick_id;
END;
$$;
