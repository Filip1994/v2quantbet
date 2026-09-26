-- QuantLab Task 003: CornerLab/CardLab shadow decision ledger.
-- These tables are append-only and never mutate production pick/model/bankroll state.

CREATE TABLE quantlab_context_market_decisions (
    decision_id TEXT PRIMARY KEY
        CHECK (decision_id ~ '^quantlab-context-decision-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    lab TEXT NOT NULL CHECK (lab IN ('CORNER', 'CARD')),
    decision_at TIMESTAMPTZ NOT NULL,
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    model_name TEXT,
    model_version TEXT,
    bookmaker_id BIGINT CHECK (bookmaker_id IS NULL OR bookmaker_id IN (8, 11)),
    bookmaker_name TEXT,
    reference_bookmaker_id BIGINT
        CHECK (reference_bookmaker_id IS NULL OR reference_bookmaker_id IN (8, 11)),
    reference_bookmaker_name TEXT,
    provider_bet_id BIGINT CHECK (provider_bet_id IS NULL OR provider_bet_id > 0),
    provider_bet_name TEXT,
    market_key TEXT,
    selection TEXT,
    line NUMERIC(12,4),
    selected_observation_id TEXT REFERENCES quantlab_market_observations(market_observation_id),
    companion_observation_id TEXT REFERENCES quantlab_market_observations(market_observation_id),
    reference_observation_id TEXT REFERENCES quantlab_market_observations(market_observation_id),
    reference_companion_observation_id TEXT
        REFERENCES quantlab_market_observations(market_observation_id),
    quote_observed_at TIMESTAMPTZ,
    reference_quote_observed_at TIMESTAMPTZ,
    odds NUMERIC(14,6) CHECK (odds IS NULL OR odds > 1),
    companion_odds NUMERIC(14,6) CHECK (companion_odds IS NULL OR companion_odds > 1),
    reference_odds NUMERIC(14,6) CHECK (reference_odds IS NULL OR reference_odds > 1),
    reference_companion_odds NUMERIC(14,6)
        CHECK (reference_companion_odds IS NULL OR reference_companion_odds > 1),
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        decision = 'PASS'
        OR (
            bookmaker_id IS NOT NULL
            AND reference_bookmaker_id IS NOT NULL
            AND bookmaker_id <> reference_bookmaker_id
            AND provider_bet_id IS NOT NULL
            AND market_key IS NOT NULL
            AND selection IN ('OVER', 'UNDER')
            AND line IS NOT NULL
            AND selected_observation_id IS NOT NULL
            AND companion_observation_id IS NOT NULL
            AND reference_observation_id IS NOT NULL
            AND reference_companion_observation_id IS NOT NULL
            AND quote_observed_at IS NOT NULL
            AND reference_quote_observed_at IS NOT NULL
            AND odds IS NOT NULL
            AND companion_odds IS NOT NULL
            AND reference_odds IS NOT NULL
            AND reference_companion_odds IS NOT NULL
            AND market_probability IS NOT NULL
            AND model_probability IS NOT NULL
            AND edge IS NOT NULL
            AND expected_value IS NOT NULL
        )
    )
);

CREATE INDEX idx_quantlab_context_decisions_fixture
    ON quantlab_context_market_decisions (lab, fixture_id, decision_at DESC);

CREATE INDEX idx_quantlab_context_decisions_market
    ON quantlab_context_market_decisions
    (lab, market_key, line, decision_at DESC)
    WHERE market_key IS NOT NULL;

CREATE UNIQUE INDEX uq_quantlab_context_decisions_first_pick
    ON quantlab_context_market_decisions
    (lab, fixture_id, market_key, COALESCE(line, -1), policy_version)
    WHERE decision = 'PICK';

CREATE TRIGGER quantlab_context_market_decisions_immutable
BEFORE UPDATE OR DELETE ON quantlab_context_market_decisions
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
