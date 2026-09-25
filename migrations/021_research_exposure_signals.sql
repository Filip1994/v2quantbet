-- QuantBet: durable exposure-blocked research signals and bankroll-free quote tracking

CREATE TABLE research_signals (
    signal_id TEXT PRIMARY KEY
        CHECK (signal_id ~ '^research-signal-v1:[0-9a-f]{64}$'),
    evaluation_id TEXT NOT NULL UNIQUE
        REFERENCES value_evaluations(evaluation_id) ON DELETE RESTRICT,
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    blocked_reason TEXT NOT NULL
        CHECK (blocked_reason = 'MAX_OPEN_EXPOSURE_EXCEEDED'),
    registration_policy_fingerprint TEXT NOT NULL
        CHECK (length(trim(registration_policy_fingerprint)) > 0),
    allowed_fixture_statuses TEXT[] NOT NULL
        CHECK (cardinality(allowed_fixture_statuses) > 0),
    maximum_quote_age_seconds INTEGER NOT NULL CHECK (maximum_quote_age_seconds >= 0),
    capture_source TEXT NOT NULL DEFAULT 'LIVE'
        CHECK (capture_source IN ('LIVE', 'LOG_BACKFILL')),
    detected_at TIMESTAMPTZ NOT NULL,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (signal_id, fixture_id)
);

CREATE INDEX idx_research_signals_fixture
    ON research_signals (fixture_id, detected_at, signal_id);
CREATE INDEX idx_research_signals_detected
    ON research_signals (detected_at DESC, signal_id);

CREATE TABLE research_signal_monitoring_states (
    signal_id TEXT PRIMARY KEY REFERENCES research_signals(signal_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('MONITORING', 'CLOSED_FOR_ODDS')),
    lifecycle_policy_version TEXT NOT NULL
        CHECK (lifecycle_policy_version = 'ODDS_LIFECYCLE_V1'),
    monitoring_interval_seconds INTEGER NOT NULL CHECK (monitoring_interval_seconds > 0),
    current_max_age_seconds INTEGER NOT NULL CHECK (current_max_age_seconds > 0),
    closing_max_age_seconds INTEGER NOT NULL CHECK (closing_max_age_seconds > 0),
    started_at TIMESTAMPTZ NOT NULL,
    next_refresh_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL CHECK (version > 0),
    CHECK (
        (state = 'MONITORING' AND next_refresh_at IS NOT NULL)
        OR (state = 'CLOSED_FOR_ODDS' AND next_refresh_at IS NULL)
    )
);

CREATE INDEX idx_research_signal_monitoring_due
    ON research_signal_monitoring_states (next_refresh_at, signal_id)
    WHERE state = 'MONITORING';

CREATE TABLE research_signal_closing_finalizations (
    finalization_id TEXT PRIMARY KEY
        CHECK (finalization_id ~ '^research-closing-finalization-v1:[0-9a-f]{64}$'),
    signal_id TEXT NOT NULL UNIQUE,
    fixture_id TEXT NOT NULL,
    fixture_observation_id TEXT NOT NULL,
    cutoff_at TIMESTAMPTZ NOT NULL,
    series_id TEXT NOT NULL REFERENCES quote_series(series_id) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    finalized_at TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('CAPTURED', 'NO_VALID_QUOTE', 'STALE_QUOTE')),
    candidate_snapshot_id TEXT,
    closing_snapshot_id TEXT,
    lifecycle_policy_version TEXT NOT NULL
        CHECK (lifecycle_policy_version = 'ODDS_LIFECYCLE_V1'),
    closing_max_age_seconds INTEGER NOT NULL CHECK (closing_max_age_seconds > 0),
    FOREIGN KEY (signal_id, fixture_id)
        REFERENCES research_signals(signal_id, fixture_id) ON DELETE RESTRICT,
    FOREIGN KEY (fixture_observation_id, fixture_id)
        REFERENCES fixture_observations(fixture_observation_id, fixture_id) ON DELETE RESTRICT,
    FOREIGN KEY (candidate_snapshot_id, series_id, source)
        REFERENCES quote_snapshots(snapshot_id, series_id, source) ON DELETE RESTRICT,
    FOREIGN KEY (closing_snapshot_id, series_id, source)
        REFERENCES quote_snapshots(snapshot_id, series_id, source) ON DELETE RESTRICT,
    CHECK (finalized_at >= cutoff_at),
    CHECK (
        (outcome = 'CAPTURED' AND candidate_snapshot_id IS NOT NULL
            AND closing_snapshot_id = candidate_snapshot_id)
        OR
        (outcome = 'NO_VALID_QUOTE' AND candidate_snapshot_id IS NULL
            AND closing_snapshot_id IS NULL)
        OR
        (outcome = 'STALE_QUOTE' AND candidate_snapshot_id IS NOT NULL
            AND closing_snapshot_id IS NULL)
    )
);

CREATE INDEX idx_research_signal_closing_cutoff
    ON research_signal_closing_finalizations (cutoff_at, signal_id);

CREATE FUNCTION reject_research_signal_fact_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'research signal facts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_signals_append_only
    BEFORE UPDATE OR DELETE ON research_signals
    FOR EACH ROW EXECUTE FUNCTION reject_research_signal_fact_mutation();

CREATE TRIGGER research_signal_closing_finalizations_append_only
    BEFORE UPDATE OR DELETE ON research_signal_closing_finalizations
    FOR EACH ROW EXECUTE FUNCTION reject_research_signal_fact_mutation();
