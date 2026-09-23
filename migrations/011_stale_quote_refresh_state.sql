-- Durable, replay-safe provider-observation freshness scheduling state.

CREATE TABLE production_quote_refresh_states (
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id),
    bookmaker_id INTEGER NOT NULL CHECK (bookmaker_id > 0),
    freshness_state TEXT NOT NULL CHECK (
        freshness_state IN ('FRESH', 'STALE', 'NO_USABLE_QUOTE')
    ),
    stale_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (stale_attempt_count >= 0),
    first_stale_at TIMESTAMPTZ,
    last_attempt_at TIMESTAMPTZ NOT NULL,
    next_retry_at TIMESTAMPTZ,
    latest_observed_at TIMESTAMPTZ,
    latest_captured_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (fixture_id, bookmaker_id),
    CHECK (
        (freshness_state = 'STALE' AND stale_attempt_count > 0 AND first_stale_at IS NOT NULL
            AND latest_observed_at IS NOT NULL AND latest_captured_at IS NOT NULL)
        OR
        (freshness_state <> 'STALE' AND stale_attempt_count = 0 AND first_stale_at IS NULL
            AND next_retry_at IS NULL)
    )
);

CREATE INDEX idx_production_quote_refresh_retry
    ON production_quote_refresh_states (freshness_state, next_retry_at, fixture_id);
