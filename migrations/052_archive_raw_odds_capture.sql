-- Archive raw provider odds once per QuantLab market capture.
-- Normalized market observations can then stay compact while the exact source payload
-- remains retrievable from Durable Barrel.

ALTER TABLE quantlab_market_captures
    ADD COLUMN IF NOT EXISTS archive_dataset TEXT,
    ADD COLUMN IF NOT EXISTS archive_object_key TEXT,
    ADD COLUMN IF NOT EXISTS archive_content_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS archive_compressed_bytes BIGINT;

ALTER TABLE quantlab_market_captures
    ADD CONSTRAINT quantlab_market_capture_archive_metadata_complete
    CHECK (
        (archive_dataset IS NULL
         AND archive_object_key IS NULL
         AND archive_content_sha256 IS NULL
         AND archive_compressed_bytes IS NULL)
        OR
        (archive_dataset IS NOT NULL
         AND archive_object_key IS NOT NULL
         AND archive_content_sha256 ~ '^[0-9a-f]{64}$'
         AND archive_compressed_bytes >= 0)
    );

CREATE INDEX IF NOT EXISTS idx_quantlab_market_captures_archive_object
    ON quantlab_market_captures (archive_object_key)
    WHERE archive_object_key IS NOT NULL;
