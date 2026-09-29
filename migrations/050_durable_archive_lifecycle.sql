-- Durable Barrel lifecycle V1.
-- Keep live/decision evidence in PostgreSQL while allowing verified cold-market rows
-- to leave the hot database after their retention window.

CREATE TABLE IF NOT EXISTS cold_archive_watermarks (
    dataset TEXT PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL,
    record_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_quantlab_market_archive_cutoff
    ON quantlab_market_observations USING BRIN (captured_at)
    WITH (pages_per_range = 64);

CREATE INDEX IF NOT EXISTS idx_quantlab_goal_decisions_selected_observation
    ON quantlab_goal_decisions (selected_observation_id)
    WHERE selected_observation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quantlab_goal_decisions_companion_observation
    ON quantlab_goal_decisions (companion_observation_id)
    WHERE companion_observation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_quantlab_context_decisions_selected_observation
    ON quantlab_context_market_decisions (selected_observation_id)
    WHERE selected_observation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quantlab_context_decisions_companion_observation
    ON quantlab_context_market_decisions (companion_observation_id)
    WHERE companion_observation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quantlab_context_decisions_reference_observation
    ON quantlab_context_market_decisions (reference_observation_id)
    WHERE reference_observation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quantlab_context_decisions_reference_companion_observation
    ON quantlab_context_market_decisions (reference_companion_observation_id)
    WHERE reference_companion_observation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_quantlab_goal_picks_selected_observation
    ON quantlab_goal_picks (selected_observation_id);
CREATE INDEX IF NOT EXISTS idx_quantlab_goal_picks_companion_observation
    ON quantlab_goal_picks (companion_observation_id);

CREATE OR REPLACE FUNCTION quantlab_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('quantbet.archive_maintenance', true) = 'on'
    THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'QuantLab observation/snapshot tables are append-only';
END;
$$;
