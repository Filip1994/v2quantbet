-- Keep optimizer retry state per dataset without changing existing model artifacts.
ALTER TABLE model_coverage_scopes
    ADD COLUMN failed_dataset_sha256 TEXT CHECK (
        failed_dataset_sha256 IS NULL OR failed_dataset_sha256 ~ '^[0-9a-f]{64}$'
    ),
    ADD COLUMN failure_streak INTEGER NOT NULL DEFAULT 0 CHECK (failure_streak >= 0);
