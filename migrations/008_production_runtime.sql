-- QuantBet Task #13: production runtime status and bounded item failures

CREATE TABLE production_worker_status (
    worker_name TEXT PRIMARY KEY CHECK (length(trim(worker_name)) > 0),
    last_started_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    next_due_at TIMESTAMPTZ,
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    cycle_count BIGINT NOT NULL DEFAULT 0 CHECK (cycle_count >= 0),
    success_count BIGINT NOT NULL DEFAULT 0 CHECK (success_count >= 0),
    failure_count BIGINT NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    last_error_class TEXT,
    last_error_message TEXT CHECK (
        last_error_message IS NULL OR length(last_error_message) <= 500
    ),
    instance_id TEXT NOT NULL CHECK (length(trim(instance_id)) > 0),
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE production_item_failures (
    worker_name TEXT NOT NULL CHECK (length(trim(worker_name)) > 0),
    item_id TEXT NOT NULL CHECK (length(trim(item_id)) > 0),
    failure_count BIGINT NOT NULL CHECK (failure_count > 0),
    last_failure_at TIMESTAMPTZ NOT NULL,
    next_retry_at TIMESTAMPTZ NOT NULL,
    last_error_class TEXT NOT NULL CHECK (length(trim(last_error_class)) > 0),
    last_error_message TEXT NOT NULL CHECK (length(last_error_message) <= 500),
    PRIMARY KEY (worker_name, item_id)
);

CREATE INDEX idx_production_item_failures_retry
    ON production_item_failures (worker_name, next_retry_at, item_id);
