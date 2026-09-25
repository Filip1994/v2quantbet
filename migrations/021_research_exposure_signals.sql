-- Durable shadow/research capture for otherwise-qualified signals blocked only by exposure.
-- These rows never reserve bankroll and exist solely for later calibration/CLV/outcome analysis.

CREATE TABLE research_exposure_signals (
    evaluation_id TEXT PRIMARY KEY
        REFERENCES value_evaluations(evaluation_id) ON DELETE RESTRICT,
    first_blocked_at TIMESTAMPTZ NOT NULL,
    last_blocked_at TIMESTAMPTZ NOT NULL,
    block_count INTEGER NOT NULL DEFAULT 1 CHECK (block_count > 0),
    first_open_exposure_minor BIGINT NOT NULL CHECK (first_open_exposure_minor >= 0),
    last_open_exposure_minor BIGINT NOT NULL CHECK (last_open_exposure_minor >= 0),
    max_open_exposure_minor BIGINT NOT NULL CHECK (max_open_exposure_minor > 0),
    fixed_stake_minor BIGINT NOT NULL CHECK (fixed_stake_minor > 0),
    capture_origin TEXT NOT NULL DEFAULT 'LIVE'
        CHECK (capture_origin IN ('LIVE', 'LOG_BACKFILL')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_research_exposure_signals_blocked_at
    ON research_exposure_signals (first_blocked_at DESC, evaluation_id);

CREATE INDEX idx_research_exposure_signals_last_blocked_at
    ON research_exposure_signals (last_blocked_at DESC, evaluation_id);
