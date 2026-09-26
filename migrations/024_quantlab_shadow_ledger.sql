-- QuantLab: isolated shadow-bet ledger and API usage category.
-- QuantLab never writes production picks, decisions, bankroll, or active model state.

ALTER TABLE provider_request_usage
    DROP CONSTRAINT provider_request_usage_category_check;

ALTER TABLE provider_request_usage
    ADD CONSTRAINT provider_request_usage_category_check CHECK (category IN (
        'discovery',
        'model_training',
        'opportunity_odds',
        'results_monitoring',
        'quantlab_context'
    ));

CREATE TABLE quantlab_shadow_bets (
    shadow_bet_id TEXT PRIMARY KEY
        CHECK (shadow_bet_id ~ '^quantlab-shadow-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    lab TEXT NOT NULL CHECK (lab IN ('GOAL', 'CORNER', 'CARD')),
    bookmaker_id BIGINT NOT NULL CHECK (bookmaker_id IN (8, 11)),
    bookmaker_name TEXT NOT NULL,
    provider_bet_id BIGINT NOT NULL CHECK (provider_bet_id > 0),
    provider_bet_name TEXT NOT NULL,
    market_key TEXT NOT NULL,
    selection TEXT NOT NULL,
    line NUMERIC(10,3),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_probability NUMERIC(12,9) NOT NULL
        CHECK (model_probability > 0 AND model_probability < 1),
    market_probability NUMERIC(12,9)
        CHECK (market_probability IS NULL OR (market_probability > 0 AND market_probability < 1)),
    edge NUMERIC(12,9),
    expected_value NUMERIC(12,9),
    odds NUMERIC(12,5) NOT NULL CHECK (odds > 1),
    quote_observed_at TIMESTAMPTZ NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    closing_odds NUMERIC(12,5) CHECK (closing_odds IS NULL OR closing_odds > 1),
    closing_observed_at TIMESTAMPTZ,
    stake_minor BIGINT NOT NULL CHECK (stake_minor > 0),
    outcome TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (outcome IN ('PENDING', 'WIN', 'LOSS', 'VOID')),
    pnl_minor BIGINT,
    settled_at TIMESTAMPTZ,
    result_detail JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((closing_odds IS NULL) = (closing_observed_at IS NULL)),
    CHECK (
        (outcome = 'PENDING' AND pnl_minor IS NULL AND settled_at IS NULL)
        OR
        (outcome <> 'PENDING' AND pnl_minor IS NOT NULL AND settled_at IS NOT NULL)
    )
);

CREATE INDEX idx_quantlab_shadow_bets_lab_decision
    ON quantlab_shadow_bets (lab, decision_at DESC);

CREATE INDEX idx_quantlab_shadow_bets_market
    ON quantlab_shadow_bets (lab, market_key, bookmaker_id, decision_at DESC);

CREATE INDEX idx_quantlab_shadow_bets_settlement
    ON quantlab_shadow_bets (lab, outcome, settled_at DESC);
