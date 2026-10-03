-- Production Funnel V1: source-agnostic clone registry.
--
-- Production has no model/pick authority of its own. It clones picks that satisfy the
-- active intake contract in Research/QuantLab and keeps only operational state here.

CREATE TABLE production_funnel_picks (
    pick_id TEXT PRIMARY KEY
        CHECK (pick_id ~ '^production-pick-v1:[0-9a-f]{64}$'),
    source_universe TEXT NOT NULL
        CHECK (source_universe IN ('RESEARCH', 'GOALLAB', 'CORNERLAB', 'CARDLAB')),
    source_pick_id TEXT NOT NULL CHECK (length(trim(source_pick_id)) > 0),
    source_fixture_id TEXT NOT NULL CHECK (length(trim(source_fixture_id)) > 0),
    intake_contract_version TEXT NOT NULL CHECK (length(trim(intake_contract_version)) > 0),
    matched_bucket_ids TEXT[] NOT NULL CHECK (cardinality(matched_bucket_ids) > 0),
    bucket_priority INTEGER NOT NULL CHECK (bucket_priority > 0),
    home_team TEXT NOT NULL CHECK (length(trim(home_team)) > 0),
    away_team TEXT NOT NULL CHECK (length(trim(away_team)) > 0),
    competition_name TEXT NOT NULL CHECK (length(trim(competition_name)) > 0),
    country TEXT NOT NULL CHECK (length(trim(country)) > 0),
    provider_status TEXT NOT NULL CHECK (length(trim(provider_status)) > 0),
    market_key TEXT NOT NULL CHECK (length(trim(market_key)) > 0),
    selection TEXT NOT NULL CHECK (length(trim(selection)) > 0),
    line NUMERIC(10,3),
    bookmaker_id BIGINT,
    bookmaker_name TEXT NOT NULL CHECK (length(trim(bookmaker_name)) > 0),
    odds NUMERIC(12,5) NOT NULL CHECK (odds > 1),
    market_probability NUMERIC(12,9)
        CHECK (market_probability IS NULL OR (market_probability > 0 AND market_probability < 1)),
    model_probability NUMERIC(12,9)
        CHECK (model_probability IS NULL OR (model_probability > 0 AND model_probability < 1)),
    edge NUMERIC(12,9),
    expected_value NUMERIC(12,9),
    source_model_name TEXT,
    source_model_version TEXT,
    source_policy_version TEXT,
    source_quote_observed_at TIMESTAMPTZ,
    source_decision_at TIMESTAMPTZ NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    cloned_at TIMESTAMPTZ NOT NULL,
    stake_minor BIGINT NOT NULL CHECK (stake_minor > 0),
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (source_decision_at < kickoff_at),
    CHECK (cloned_at < kickoff_at),
    UNIQUE (source_universe, source_pick_id),
    UNIQUE (source_fixture_id)
);

CREATE INDEX idx_production_funnel_kickoff
    ON production_funnel_picks (kickoff_at, bucket_priority, cloned_at, pick_id);
CREATE INDEX idx_production_funnel_source
    ON production_funnel_picks (source_universe, source_decision_at DESC, source_pick_id);
CREATE INDEX idx_production_funnel_buckets
    ON production_funnel_picks USING GIN (matched_bucket_ids);

CREATE TABLE production_funnel_state_events (
    event_id TEXT PRIMARY KEY
        CHECK (event_id ~ '^production-state-event-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL
        REFERENCES production_funnel_picks(pick_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('PLAYED', 'SKIPPED')),
    occurred_at TIMESTAMPTZ NOT NULL,
    request_id TEXT NOT NULL UNIQUE CHECK (length(trim(request_id)) > 0),
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_production_funnel_state_pick
    ON production_funnel_state_events
    (pick_id, occurred_at DESC, persisted_at DESC, event_id DESC);

CREATE OR REPLACE FUNCTION reject_production_funnel_fact_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Production funnel facts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER production_funnel_picks_append_only
    BEFORE UPDATE OR DELETE ON production_funnel_picks
    FOR EACH ROW EXECUTE FUNCTION reject_production_funnel_fact_mutation();

CREATE TRIGGER production_funnel_state_events_append_only
    BEFORE UPDATE OR DELETE ON production_funnel_state_events
    FOR EACH ROW EXECUTE FUNCTION reject_production_funnel_fact_mutation();
