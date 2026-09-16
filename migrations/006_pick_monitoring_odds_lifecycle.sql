-- QuantBet — durable registered-pick monitoring and immutable closing facts

ALTER TABLE registered_picks
    ADD CONSTRAINT registered_picks_pick_fixture_key UNIQUE (pick_id, fixture_id);

ALTER TABLE quote_snapshots
    ADD CONSTRAINT quote_snapshots_snapshot_series_source_key
    UNIQUE (snapshot_id, series_id, source);

CREATE TABLE pick_monitoring_states (
    pick_id TEXT PRIMARY KEY REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('MONITORING', 'CLOSED_FOR_ODDS')),
    lifecycle_policy_version TEXT NOT NULL CHECK (lifecycle_policy_version = 'ODDS_LIFECYCLE_V1'),
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

CREATE INDEX idx_pick_monitoring_due
    ON pick_monitoring_states (next_refresh_at, pick_id)
    WHERE state = 'MONITORING';

CREATE TABLE pick_monitoring_transitions (
    transition_id TEXT PRIMARY KEY
        CHECK (transition_id ~ '^pick-monitoring-transition-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    transition_type TEXT NOT NULL CHECK (transition_type IN ('MONITORING_STARTED', 'ODDS_CLOSED')),
    from_state TEXT NOT NULL CHECK (from_state IN ('REGISTERED', 'MONITORING')),
    to_state TEXT NOT NULL CHECK (to_state IN ('MONITORING', 'CLOSED_FOR_ODDS')),
    occurred_at TIMESTAMPTZ NOT NULL,
    UNIQUE (pick_id, transition_type),
    CHECK (
        (transition_type = 'MONITORING_STARTED' AND from_state = 'REGISTERED'
            AND to_state = 'MONITORING')
        OR
        (transition_type = 'ODDS_CLOSED' AND from_state = 'MONITORING'
            AND to_state = 'CLOSED_FOR_ODDS')
    )
);

CREATE INDEX idx_pick_monitoring_transition_history
    ON pick_monitoring_transitions (pick_id, occurred_at, transition_id);

CREATE TABLE pick_closing_finalizations (
    finalization_id TEXT PRIMARY KEY
        CHECK (finalization_id ~ '^pick-closing-finalization-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL UNIQUE,
    fixture_id TEXT NOT NULL,
    fixture_observation_id TEXT NOT NULL,
    cutoff_at TIMESTAMPTZ NOT NULL,
    series_id TEXT NOT NULL REFERENCES quote_series(series_id) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    finalized_at TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('CAPTURED', 'NO_VALID_QUOTE', 'STALE_QUOTE')),
    candidate_snapshot_id TEXT,
    closing_snapshot_id TEXT,
    lifecycle_policy_version TEXT NOT NULL CHECK (lifecycle_policy_version = 'ODDS_LIFECYCLE_V1'),
    closing_max_age_seconds INTEGER NOT NULL CHECK (closing_max_age_seconds > 0),
    FOREIGN KEY (pick_id, fixture_id)
        REFERENCES registered_picks(pick_id, fixture_id) ON DELETE RESTRICT,
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

CREATE INDEX idx_pick_closing_cutoff
    ON pick_closing_finalizations (cutoff_at, pick_id);

CREATE INDEX idx_quote_snapshots_lifecycle_opening
    ON quote_snapshots (series_id, source, captured_at, observed_at, snapshot_id);

CREATE INDEX idx_quote_snapshots_lifecycle_latest
    ON quote_snapshots
    (series_id, source, observed_at DESC, captured_at DESC, snapshot_id DESC);

CREATE FUNCTION reject_pick_lifecycle_fact_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'pick lifecycle facts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pick_monitoring_transitions_append_only
    BEFORE UPDATE OR DELETE ON pick_monitoring_transitions
    FOR EACH ROW EXECUTE FUNCTION reject_pick_lifecycle_fact_mutation();

CREATE TRIGGER pick_closing_finalizations_immutable
    BEFORE UPDATE OR DELETE ON pick_closing_finalizations
    FOR EACH ROW EXECUTE FUNCTION reject_pick_lifecycle_fact_mutation();
