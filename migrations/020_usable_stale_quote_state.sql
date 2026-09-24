-- Distinguish provider snapshots that are old but still allowed for candidate evaluation.
-- USABLE_STALE carries quote-age provenance without activating the accelerated retry path.

ALTER TABLE production_quote_refresh_states
    DROP CONSTRAINT IF EXISTS production_quote_refresh_states_freshness_state_check;

ALTER TABLE production_quote_refresh_states
    ADD CONSTRAINT production_quote_refresh_states_freshness_state_check
    CHECK (freshness_state IN ('FRESH', 'USABLE_STALE', 'STALE', 'NO_USABLE_QUOTE'));
