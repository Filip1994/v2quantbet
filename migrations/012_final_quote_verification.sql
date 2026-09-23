-- Mandatory, auditable final quote verification before a pick can be approved.

CREATE TABLE final_quote_verifications (
    verification_id TEXT PRIMARY KEY
        CHECK (verification_id ~ '^final-quote-verification-v1:[0-9a-f]{64}$'),
    preliminary_evaluation_id TEXT NOT NULL UNIQUE
        REFERENCES value_evaluations(evaluation_id) ON DELETE RESTRICT,
    fixture_id TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('OU_25', 'BTTS')),
    selection TEXT NOT NULL,
    bookmaker_id BIGINT NOT NULL CHECK (bookmaker_id > 0),
    requested_provider TEXT NOT NULL CHECK (length(trim(requested_provider)) > 0),
    requested_at TIMESTAMPTZ NOT NULL,
    budget_outcome TEXT NOT NULL CHECK (budget_outcome IN ('PENDING', 'ALLOWED', 'DENIED')),
    status TEXT NOT NULL CHECK (status IN ('REQUESTED', 'READY', 'REJECTED')),
    returned_source TEXT,
    returned_bookmaker_key TEXT,
    returned_observed_at TIMESTAMPTZ,
    returned_captured_at TIMESTAMPTZ,
    quote_age_seconds DOUBLE PRECISION CHECK (
        quote_age_seconds IS NULL OR quote_age_seconds >= 0
    ),
    stale_quote BOOLEAN NOT NULL DEFAULT FALSE,
    warning_codes TEXT[] NOT NULL DEFAULT '{}',
    returned_snapshot_ids TEXT[] NOT NULL DEFAULT '{}',
    final_evaluation_id TEXT UNIQUE
        REFERENCES value_evaluations(evaluation_id) ON DELETE RESTRICT,
    final_odd DOUBLE PRECISION,
    final_devig_probability DOUBLE PRECISION,
    final_model_probability DOUBLE PRECISION,
    final_edge DOUBLE PRECISION,
    final_expected_value DOUBLE PRECISION,
    minimum_playable_odds DOUBLE PRECISION CHECK (
        minimum_playable_odds IS NULL OR minimum_playable_odds > 1
    ),
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    decided_at TIMESTAMPTZ,
    CHECK (
        (status = 'REQUESTED' AND budget_outcome = 'PENDING'
            AND final_evaluation_id IS NULL AND decided_at IS NULL)
        OR
        (status = 'READY' AND budget_outcome = 'ALLOWED'
            AND final_evaluation_id IS NOT NULL AND returned_source IS NOT NULL
            AND returned_bookmaker_key IS NOT NULL AND returned_observed_at IS NOT NULL
            AND returned_captured_at IS NOT NULL AND quote_age_seconds IS NOT NULL
            AND cardinality(returned_snapshot_ids) = 2 AND final_odd IS NOT NULL
            AND final_devig_probability IS NOT NULL AND final_model_probability IS NOT NULL
            AND final_edge IS NOT NULL AND final_expected_value IS NOT NULL
            AND minimum_playable_odds IS NOT NULL
            AND cardinality(reason_codes) = 0 AND decided_at IS NOT NULL)
        OR
        (status = 'REJECTED' AND budget_outcome IN ('ALLOWED', 'DENIED')
            AND cardinality(reason_codes) > 0 AND decided_at IS NOT NULL)
    )
);

CREATE INDEX idx_final_quote_verifications_fixture
    ON final_quote_verifications (fixture_id, requested_at, verification_id);
CREATE INDEX idx_final_quote_verifications_status
    ON final_quote_verifications (status, requested_at, verification_id);

ALTER TABLE pick_decisions
    ADD COLUMN final_quote_verification_id TEXT
        REFERENCES final_quote_verifications(verification_id) ON DELETE RESTRICT;
