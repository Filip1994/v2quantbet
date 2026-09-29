-- Lossless cold archive catalog for S3-compatible object storage.
-- Operational/live records stay in PostgreSQL; immutable cold batches are indexed here.

CREATE TABLE IF NOT EXISTS cold_archive_batches (
    archive_batch_id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    object_key TEXT NOT NULL UNIQUE,
    format TEXT NOT NULL CHECK (format IN ('jsonl+gzip')),
    min_recorded_at TIMESTAMPTZ,
    max_recorded_at TIMESTAMPTZ,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    compressed_bytes BIGINT NOT NULL CHECK (compressed_bytes >= 0),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMPTZ NOT NULL,
    deleted_from_hot_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_cold_archive_batches_dataset_time
    ON cold_archive_batches (dataset, min_recorded_at, max_recorded_at, created_at);
