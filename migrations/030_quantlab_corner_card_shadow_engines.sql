-- QuantLab Task 003: append-only CornerLab/CardLab shadow decision evidence.
-- Production prediction, registration, bankroll and active-model state remain untouched.

CREATE TABLE quantlab_count_decisions (
    decision_id TEXT PRIMARY KEY
        CHECK (decision_id ~ '^quantlab-count-decision-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    lab TEXT NOT NULL CHECK (lab IN ('CORNER', 'CARD')),
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
    line NUMERIC(10,3),
    selected_observation_id TEXT REFERENCES quantlab_market_observations(market_observation_id)
        ON DELETE RESTRICT,
    companion_observation_id TEXT REFERENCES quantlab_market_observations(market_observation_id)
        ON DELETE RESTRICT,
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
    evidence_fingerprint TEXT NOT NULL CHECK (evidence_fingerprint ~ '^[0-9a-f]{64}$'),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_count_decisions_fixture
    ON quantlab_count_decisions (lab, fixture_id, decision_at DESC);

CREATE INDEX idx_quantlab_count_decisions_policy
    ON quantlab_count_decisions (lab, policy_version, decision_at DESC);

CREATE UNIQUE INDEX uq_quantlab_count_decisions_first_pick
    ON quantlab_count_decisions (
        lab,
        fixture_id,
        market_key,
        selection,
        COALESCE(line, -1),
        policy_version
    )
    WHERE decision = 'PICK';

CREATE TRIGGER quantlab_count_decisions_immutable
BEFORE UPDATE OR DELETE ON quantlab_count_decisions
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
