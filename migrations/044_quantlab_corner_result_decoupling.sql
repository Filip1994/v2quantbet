-- Restore QuantLab isolation from the shared production result ledger.
-- QuantLab corner settlement rows keep the immutable result_observation_id as provenance
-- text, but must not own a foreign key that prevents independent production result-table
-- maintenance or test cleanup.

ALTER TABLE quantlab_corner_settlement_events
    DROP CONSTRAINT IF EXISTS
    quantlab_corner_settlement_events_result_observation_id_fkey;
