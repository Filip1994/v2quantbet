-- Durable production Dixon-Coles coverage, acquisition replay safety, and provider budgets.

CREATE TABLE model_coverage_scopes (
    provider TEXT NOT NULL CHECK (provider = 'api-football'),
    team_id_namespace TEXT NOT NULL CHECK (team_id_namespace = 'api-football'),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER NOT NULL CHECK (season > 0),
    status TEXT NOT NULL CHECK (status IN (
        'ACTIVE', 'MISSING', 'TRAINING_REQUIRED', 'TRAINING_PENDING',
        'INSUFFICIENT_DATA', 'TRAINING_FAILED', 'STALE', 'RETRAIN_REQUIRED'
    )),
    eligible BOOLEAN NOT NULL DEFAULT TRUE,
    first_required_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    next_attempt_at TIMESTAMPTZ,
    training_started_at TIMESTAMPTZ,
    training_finished_at TIMESTAMPTZ,
    attempt_count BIGINT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    accepted_match_count INTEGER CHECK (accepted_match_count >= 0),
    fitted_match_count INTEGER CHECK (fitted_match_count >= 0),
    last_training_duration_seconds DOUBLE PRECISION CHECK (
        last_training_duration_seconds >= 0
        AND last_training_duration_seconds < 'Infinity'::double precision
    ),
    last_error_class TEXT CHECK (last_error_class IS NULL OR length(last_error_class) <= 100),
    last_error_message TEXT CHECK (last_error_message IS NULL OR length(last_error_message) <= 500),
    active_model_version_id TEXT,
    active_generation BIGINT CHECK (active_generation > 0),
    policy_fingerprint TEXT NOT NULL CHECK (policy_fingerprint ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (provider, team_id_namespace, league_id, season),
    CHECK ((active_model_version_id IS NULL) = (active_generation IS NULL))
);

CREATE INDEX idx_model_coverage_training_queue
    ON model_coverage_scopes (status, next_attempt_at, first_required_at, league_id, season);

CREATE TABLE model_training_acquisitions (
    provider TEXT NOT NULL CHECK (provider = 'api-football'),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER NOT NULL CHECK (season > 0),
    training_start_at TIMESTAMPTZ NOT NULL,
    training_end_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMPLETE', 'FAILED')),
    response_payload JSONB,
    accepted_match_count INTEGER CHECK (accepted_match_count >= 0),
    acquired_at TIMESTAMPTZ NOT NULL,
    last_error_class TEXT CHECK (last_error_class IS NULL OR length(last_error_class) <= 100),
    last_error_message TEXT CHECK (last_error_message IS NULL OR length(last_error_message) <= 500),
    PRIMARY KEY (provider, league_id, season, training_start_at, training_end_at),
    CHECK (training_start_at < training_end_at),
    CHECK (
        (status = 'COMPLETE' AND response_payload IS NOT NULL
            AND accepted_match_count IS NOT NULL AND last_error_class IS NULL)
        OR
        (status = 'FAILED' AND response_payload IS NULL AND last_error_class IS NOT NULL)
    )
);

CREATE TABLE provider_request_usage (
    request_day DATE NOT NULL,
    category TEXT NOT NULL CHECK (category IN (
        'discovery', 'model_training', 'opportunity_odds', 'results_monitoring'
    )),
    request_count BIGINT NOT NULL CHECK (request_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (request_day, category)
);
