-- QuantLab H2HLab V1: direct head-to-head snapshots, decisions and lab exposure.
-- H2HLab is isolated from GoalLab pick authority and production registration/bankroll state.

ALTER TABLE quantlab_shadow_bets
    DROP CONSTRAINT IF EXISTS quantlab_shadow_bets_lab_check;
ALTER TABLE quantlab_shadow_bets
    ADD CONSTRAINT quantlab_shadow_bets_lab_check
    CHECK (lab IN ('GOAL', 'CORNER', 'CARD', 'H2H'));

CREATE TABLE quantlab_h2h_snapshots (
    h2h_snapshot_id TEXT PRIMARY KEY
        CHECK (h2h_snapshot_id ~ '^quantlab-h2h-snapshot-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL
        REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    home_team_id BIGINT NOT NULL CHECK (home_team_id > 0),
    away_team_id BIGINT NOT NULL CHECK (away_team_id > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    sample_size INTEGER NOT NULL CHECK (sample_size >= 0 AND sample_size <= 10),
    source TEXT NOT NULL DEFAULT 'api-football:fixtures/headtohead'
        CHECK (source = 'api-football:fixtures/headtohead'),
    meetings JSONB NOT NULL,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (home_team_id <> away_team_id)
);

CREATE INDEX idx_quantlab_h2h_snapshots_fixture_capture
    ON quantlab_h2h_snapshots (fixture_id, captured_at DESC, h2h_snapshot_id DESC);

CREATE TRIGGER quantlab_h2h_snapshots_immutable
BEFORE UPDATE OR DELETE ON quantlab_h2h_snapshots
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_h2h_decisions (
    decision_id TEXT PRIMARY KEY
        CHECK (decision_id ~ '^quantlab-h2h-decision-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL
        REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    h2h_snapshot_id TEXT
        REFERENCES quantlab_h2h_snapshots(h2h_snapshot_id) ON DELETE RESTRICT,
    decision_at TIMESTAMPTZ NOT NULL,
    policy_version TEXT NOT NULL,
    model_name TEXT,
    model_version TEXT,
    bookmaker_id BIGINT CHECK (bookmaker_id IS NULL OR bookmaker_id IN (8, 11)),
    bookmaker_name TEXT,
    provider_bet_id BIGINT CHECK (provider_bet_id IS NULL OR provider_bet_id > 0),
    provider_bet_name TEXT,
    market_key TEXT,
    selection TEXT,
    line NUMERIC(12,4),
    selected_observation_id TEXT
        REFERENCES quantlab_market_observations(market_observation_id),
    companion_observation_id TEXT
        REFERENCES quantlab_market_observations(market_observation_id),
    quote_observed_at TIMESTAMPTZ,
    odds NUMERIC(14,6) CHECK (odds IS NULL OR odds > 1),
    companion_odds NUMERIC(14,6) CHECK (companion_odds IS NULL OR companion_odds > 1),
    market_probability NUMERIC(12,9)
        CHECK (market_probability IS NULL OR (market_probability > 0 AND market_probability < 1)),
    dc_probability NUMERIC(12,9)
        CHECK (dc_probability IS NULL OR (dc_probability > 0 AND dc_probability < 1)),
    h2h_probability NUMERIC(12,9)
        CHECK (h2h_probability IS NULL OR (h2h_probability > 0 AND h2h_probability < 1)),
    dc_weight NUMERIC(12,9)
        CHECK (dc_weight IS NULL OR (dc_weight >= 0 AND dc_weight <= 0.70)),
    h2h_weight NUMERIC(12,9)
        CHECK (h2h_weight IS NULL OR (h2h_weight >= 0.30 AND h2h_weight <= 1)),
    model_probability NUMERIC(12,9)
        CHECK (model_probability IS NULL OR (model_probability > 0 AND model_probability < 1)),
    edge NUMERIC(12,9),
    expected_value NUMERIC(12,9),
    h2h_sample_size INTEGER NOT NULL DEFAULT 0 CHECK (h2h_sample_size >= 0 AND h2h_sample_size <= 10),
    decision TEXT NOT NULL CHECK (decision IN ('PICK', 'PASS')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    evidence_fingerprint TEXT NOT NULL CHECK (evidence_fingerprint ~ '^[0-9a-f]{64}$'),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        dc_weight IS NULL OR h2h_weight IS NULL
        OR abs((dc_weight + h2h_weight) - 1.0) < 0.000001
    ),
    CHECK (
        decision = 'PASS'
        OR (
            h2h_snapshot_id IS NOT NULL
            AND h2h_sample_size >= 5
            AND bookmaker_id IS NOT NULL
            AND provider_bet_id IS NOT NULL
            AND market_key IN ('OU_25', 'BTTS')
            AND selection IS NOT NULL
            AND selected_observation_id IS NOT NULL
            AND companion_observation_id IS NOT NULL
            AND quote_observed_at IS NOT NULL
            AND odds IS NOT NULL
            AND companion_odds IS NOT NULL
            AND market_probability IS NOT NULL
            AND dc_probability IS NOT NULL
            AND h2h_probability IS NOT NULL
            AND dc_weight IS NOT NULL
            AND h2h_weight IS NOT NULL
            AND model_probability IS NOT NULL
            AND edge IS NOT NULL
            AND expected_value IS NOT NULL
        )
    )
);

CREATE INDEX idx_quantlab_h2h_decisions_fixture
    ON quantlab_h2h_decisions (fixture_id, decision_at DESC);
CREATE INDEX idx_quantlab_h2h_decisions_market
    ON quantlab_h2h_decisions (market_key, selection, decision_at DESC)
    WHERE market_key IS NOT NULL;
CREATE UNIQUE INDEX uq_quantlab_h2h_one_pick_per_fixture_policy
    ON quantlab_h2h_decisions (fixture_id, policy_version)
    WHERE decision = 'PICK';

CREATE TRIGGER quantlab_h2h_decisions_immutable
BEFORE UPDATE OR DELETE ON quantlab_h2h_decisions
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
