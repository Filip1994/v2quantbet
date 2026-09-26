-- QuantLab Task 002: append-only GoalLab shadow decision evidence.
-- This table records both PICK and PASS outcomes. It never mutates production decision state.

CREATE TABLE quantlab_goal_decisions (
    decision_id TEXT PRIMARY KEY
        CHECK (decision_id ~ '^quantlab-goal-decision-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    decision_at TIMESTAMPTZ NOT NULL,
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    model_name TEXT,
    model_version TEXT,
    bookmaker_id BIGINT CHECK (bookmaker_id IS NULL OR bookmaker_id IN (8, 11)),
    bookmaker_name TEXT,
    provider_bet_id BIGINT CHECK (provider_bet_id IS NULL OR provider_bet_id > 0),
    provider_bet_name TEXT,
    market_key TEXT CHECK (market_key IS NULL OR market_key IN ('OU_25', 'BTTS')),
    selection TEXT CHECK (
        selection IS NULL
        OR (market_key = 'OU_25' AND selection IN ('OVER', 'UNDER'))
        OR (market_key = 'BTTS' AND selection IN ('YES', 'NO'))
    ),
    line NUMERIC(10,3),
    selected_observation_id TEXT
        REFERENCES quantlab_market_observations(market_observation_id) ON DELETE RESTRICT,
    companion_observation_id TEXT
        REFERENCES quantlab_market_observations(market_observation_id) ON DELETE RESTRICT,
    quote_observed_at TIMESTAMPTZ,
    odds NUMERIC(12,5) CHECK (odds IS NULL OR odds > 1),
    companion_odds NUMERIC(12,5) CHECK (companion_odds IS NULL OR companion_odds > 1),
    market_probability NUMERIC(12,9)
        CHECK (market_probability IS NULL OR (market_probability > 0 AND market_probability < 1)),
    model_probability NUMERIC(12,9)
        CHECK (model_probability IS NULL OR (model_probability > 0 AND model_probability < 1)),
    edge NUMERIC(12,9),
    expected_value NUMERIC(12,9),
    decision TEXT NOT NULL CHECK (decision IN ('PICK', 'PASS')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    evidence_fingerprint TEXT NOT NULL
        CHECK (evidence_fingerprint ~ '^[0-9a-f]{64}$'),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        decision = 'PASS'
        OR (
            bookmaker_id IS NOT NULL
            AND market_key IS NOT NULL
            AND selection IS NOT NULL
            AND selected_observation_id IS NOT NULL
            AND companion_observation_id IS NOT NULL
            AND quote_observed_at IS NOT NULL
            AND odds IS NOT NULL
            AND companion_odds IS NOT NULL
            AND market_probability IS NOT NULL
            AND model_probability IS NOT NULL
            AND edge IS NOT NULL
            AND expected_value IS NOT NULL
        )
    )
);

CREATE INDEX idx_quantlab_goal_decisions_fixture
    ON quantlab_goal_decisions (fixture_id, decision_at DESC);
CREATE INDEX idx_quantlab_goal_decisions_outcome
    ON quantlab_goal_decisions (decision, decision_at DESC);
CREATE INDEX idx_quantlab_goal_decisions_market
    ON quantlab_goal_decisions (market_key, selection, bookmaker_id, decision_at DESC);

CREATE TRIGGER quantlab_goal_decisions_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_decisions
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
