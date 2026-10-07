-- KellyLab V1: immutable Research clone decisions with point-in-time Kelly sizing.
--
-- KellyLab is a shadow portfolio. It never writes Research or Production state.
-- A dedicated service creates the portfolio row on first start, then appends one
-- sizing fact per Research signal. Outcomes remain authoritative in result tables.

CREATE TABLE kellylab_portfolios (
    portfolio_id TEXT PRIMARY KEY
        CHECK (portfolio_id = 'KELLYLAB_RESEARCH_V1'),
    started_at TIMESTAMPTZ NOT NULL,
    starting_bankroll_minor BIGINT NOT NULL CHECK (starting_bankroll_minor > 0),
    flat_stake_minor BIGINT NOT NULL CHECK (flat_stake_minor > 0),
    kelly_fraction NUMERIC(12,9) NOT NULL CHECK (kelly_fraction > 0 AND kelly_fraction <= 1),
    max_bet_fraction NUMERIC(12,9) NOT NULL
        CHECK (max_bet_fraction > 0 AND max_bet_fraction <= 1),
    calibration_prior_n INTEGER NOT NULL CHECK (calibration_prior_n > 0),
    currency TEXT NOT NULL CHECK (currency = 'RSD'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE kellylab_picks (
    kelly_pick_id TEXT PRIMARY KEY
        CHECK (kelly_pick_id ~ '^kellylab-pick-v1:[0-9a-f]{64}$'),
    portfolio_id TEXT NOT NULL
        REFERENCES kellylab_portfolios(portfolio_id) ON DELETE RESTRICT,
    research_signal_id TEXT NOT NULL UNIQUE
        REFERENCES research_signals(research_signal_id) ON DELETE RESTRICT,
    fixture_id TEXT NOT NULL UNIQUE
        REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    source_decision_at TIMESTAMPTZ NOT NULL,
    materialized_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    kickoff_at TIMESTAMPTZ NOT NULL,
    home_team TEXT NOT NULL CHECK (length(trim(home_team)) > 0),
    away_team TEXT NOT NULL CHECK (length(trim(away_team)) > 0),
    competition_name TEXT NOT NULL CHECK (length(trim(competition_name)) > 0),
    country TEXT NOT NULL CHECK (length(trim(country)) > 0),
    market TEXT NOT NULL CHECK (market IN ('OU_25', 'BTTS')),
    selection TEXT NOT NULL CHECK (selection IN ('OVER', 'UNDER', 'YES', 'NO')),
    bookmaker TEXT NOT NULL CHECK (length(trim(bookmaker)) > 0),
    odds NUMERIC(12,5) NOT NULL CHECK (odds > 1),
    model_probability NUMERIC(12,9) NOT NULL
        CHECK (model_probability > 0 AND model_probability < 1),
    market_fair_probability NUMERIC(12,9) NOT NULL
        CHECK (market_fair_probability > 0 AND market_fair_probability < 1),
    edge NUMERIC(12,9) NOT NULL,
    expected_value NUMERIC(12,9) NOT NULL,
    probability_bucket TEXT NOT NULL,
    edge_bucket TEXT NOT NULL,
    odds_bucket TEXT NOT NULL,
    calibration_snapshot JSONB NOT NULL,
    calibration_gap NUMERIC(12,9) NOT NULL,
    kelly_probability NUMERIC(12,9) NOT NULL
        CHECK (kelly_probability > 0 AND kelly_probability < 1),
    raw_kelly_fraction NUMERIC(12,9) NOT NULL CHECK (raw_kelly_fraction >= 0),
    fractional_kelly_fraction NUMERIC(12,9) NOT NULL CHECK (fractional_kelly_fraction >= 0),
    applied_kelly_fraction NUMERIC(12,9) NOT NULL
        CHECK (applied_kelly_fraction >= 0 AND applied_kelly_fraction <= 1),
    bankroll_before_minor BIGINT NOT NULL CHECK (bankroll_before_minor > 0),
    stake_minor BIGINT NOT NULL CHECK (stake_minor >= 0),
    flat_stake_minor BIGINT NOT NULL CHECK (flat_stake_minor > 0),
    decision TEXT NOT NULL CHECK (decision IN ('BET', 'NO_BET')),
    contract_version TEXT NOT NULL CHECK (contract_version = 'KELLYLAB_RESEARCH_V1'),
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (source_decision_at < kickoff_at),
    CHECK (
        (decision = 'BET' AND stake_minor > 0 AND applied_kelly_fraction > 0)
        OR
        (decision = 'NO_BET' AND stake_minor = 0 AND applied_kelly_fraction = 0)
    )
);

CREATE INDEX idx_kellylab_picks_decision
    ON kellylab_picks (source_decision_at, kelly_pick_id);
CREATE INDEX idx_kellylab_picks_kickoff
    ON kellylab_picks (kickoff_at, kelly_pick_id);

CREATE OR REPLACE FUNCTION reject_kellylab_fact_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'KellyLab facts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER kellylab_portfolios_append_only
    BEFORE UPDATE OR DELETE ON kellylab_portfolios
    FOR EACH ROW EXECUTE FUNCTION reject_kellylab_fact_mutation();

CREATE TRIGGER kellylab_picks_append_only
    BEFORE UPDATE OR DELETE ON kellylab_picks
    FOR EACH ROW EXECUTE FUNCTION reject_kellylab_fact_mutation();
