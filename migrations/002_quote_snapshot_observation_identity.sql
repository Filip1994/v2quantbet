-- QuantBet — semantic identity for immutable quote observations
-- captured_at is ingestion metadata and must not define observation identity.

ALTER TABLE quote_snapshots
    DROP CONSTRAINT IF EXISTS quote_snapshots_series_id_observed_at_captured_at_source_key;

ALTER TABLE quote_snapshots
    ADD CONSTRAINT quote_snapshots_series_id_observed_at_source_key
    UNIQUE (series_id, observed_at, source);

CREATE INDEX IF NOT EXISTS idx_quote_snapshots_series_observation
    ON quote_snapshots (series_id, observed_at, source);
