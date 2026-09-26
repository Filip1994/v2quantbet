-- QuantLab Task 001: all-market observations and timestamp-safe CardLab context.
-- Production prediction/registration/bankroll tables are intentionally untouched.

CREATE OR REPLACE FUNCTION quantlab_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'QuantLab observation/snapshot tables are append-only';
END;
$$;

CREATE TABLE quantlab_market_observations (
    market_observation_id TEXT PRIMARY KEY
        CHECK (market_observation_id ~ '^quantlab-market-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    bookmaker_id BIGINT NOT NULL CHECK (bookmaker_id IN (8, 11)),
    bookmaker_name TEXT NOT NULL CHECK (length(trim(bookmaker_name)) > 0),
    provider_bet_id BIGINT NOT NULL CHECK (provider_bet_id > 0),
    provider_bet_name TEXT NOT NULL CHECK (length(trim(provider_bet_name)) > 0),
    raw_selection TEXT NOT NULL CHECK (length(trim(raw_selection)) > 0),
    parsed_line NUMERIC(12,4),
    odds NUMERIC(14,6) NOT NULL CHECK (odds > 1),
    provider_updated_at TIMESTAMPTZ,
    captured_at TIMESTAMPTZ NOT NULL,
    lab_owner TEXT NOT NULL CHECK (lab_owner IN ('GOAL', 'CORNER', 'CARD', 'UNCLASSIFIED')),
    classifier_version TEXT NOT NULL CHECK (classifier_version = 'MARKET_CLASSIFIER_V1'),
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_market_fixture_capture
    ON quantlab_market_observations (fixture_id, captured_at DESC);
CREATE INDEX idx_quantlab_market_owner
    ON quantlab_market_observations (lab_owner, provider_bet_id, captured_at DESC);

CREATE TRIGGER quantlab_market_observations_immutable
BEFORE UPDATE OR DELETE ON quantlab_market_observations
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_fixture_context_observations (
    context_observation_id TEXT PRIMARY KEY
        CHECK (context_observation_id ~ '^quantlab-context-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    referee TEXT,
    provider_status TEXT NOT NULL CHECK (length(trim(provider_status)) > 0),
    kickoff_at TIMESTAMPTZ NOT NULL,
    provider_updated_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'api-football'
        CHECK (source = 'api-football'),
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_context_fixture_available
    ON quantlab_fixture_context_observations (fixture_id, available_at DESC);
CREATE INDEX idx_quantlab_context_referee_available
    ON quantlab_fixture_context_observations (referee, available_at DESC)
    WHERE referee IS NOT NULL;

CREATE TRIGGER quantlab_fixture_context_immutable
BEFORE UPDATE OR DELETE ON quantlab_fixture_context_observations
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_match_statistics_observations (
    statistics_observation_id TEXT PRIMARY KEY
        CHECK (statistics_observation_id ~ '^quantlab-stats-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    home_fouls INTEGER CHECK (home_fouls IS NULL OR home_fouls >= 0),
    away_fouls INTEGER CHECK (away_fouls IS NULL OR away_fouls >= 0),
    home_yellow_cards INTEGER CHECK (home_yellow_cards IS NULL OR home_yellow_cards >= 0),
    away_yellow_cards INTEGER CHECK (away_yellow_cards IS NULL OR away_yellow_cards >= 0),
    home_red_cards INTEGER CHECK (home_red_cards IS NULL OR home_red_cards >= 0),
    away_red_cards INTEGER CHECK (away_red_cards IS NULL OR away_red_cards >= 0),
    home_second_yellow_cards INTEGER
        CHECK (home_second_yellow_cards IS NULL OR home_second_yellow_cards >= 0),
    away_second_yellow_cards INTEGER
        CHECK (away_second_yellow_cards IS NULL OR away_second_yellow_cards >= 0),
    available_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'api-football:fixtures/statistics'
        CHECK (source = 'api-football:fixtures/statistics'),
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_stats_fixture_available
    ON quantlab_match_statistics_observations (fixture_id, available_at DESC);

CREATE TRIGGER quantlab_match_statistics_immutable
BEFORE UPDATE OR DELETE ON quantlab_match_statistics_observations
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_standings_snapshots (
    standings_snapshot_id TEXT PRIMARY KEY
        CHECK (standings_snapshot_id ~ '^quantlab-standings-v1:[0-9a-f]{64}$'),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER NOT NULL CHECK (season > 0),
    available_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'api-football:standings'
        CHECK (source = 'api-football:standings'),
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_standings_scope_available
    ON quantlab_standings_snapshots (league_id, season, available_at DESC);

CREATE TRIGGER quantlab_standings_immutable
BEFORE UPDATE OR DELETE ON quantlab_standings_snapshots
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_card_feature_snapshots (
    feature_snapshot_id TEXT PRIMARY KEY
        CHECK (feature_snapshot_id ~ '^quantlab-card-features-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    decision_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    referee TEXT,
    referee_card_rate NUMERIC(12,6),
    referee_sample_size INTEGER NOT NULL CHECK (referee_sample_size >= 0),
    referee_foul_rate NUMERIC(12,6),
    referee_foul_sample_size INTEGER NOT NULL CHECK (referee_foul_sample_size >= 0),
    derby_rivalry_indicator SMALLINT
        CHECK (derby_rivalry_indicator IS NULL OR derby_rivalry_indicator IN (0, 1)),
    home_table_pressure NUMERIC(12,9)
        CHECK (home_table_pressure IS NULL OR (home_table_pressure >= 0 AND home_table_pressure <= 1)),
    away_table_pressure NUMERIC(12,9)
        CHECK (away_table_pressure IS NULL OR (away_table_pressure >= 0 AND away_table_pressure <= 1)),
    table_pressure NUMERIC(12,9)
        CHECK (table_pressure IS NULL OR (table_pressure >= 0 AND table_pressure <= 1)),
    match_importance NUMERIC(12,9)
        CHECK (match_importance IS NULL OR (match_importance >= 0 AND match_importance <= 1)),
    feature_version TEXT NOT NULL CHECK (feature_version = 'CARDLAB_FEATURES_V1'),
    feature_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (available_at <= decision_at),
    UNIQUE (fixture_id, decision_at, feature_version)
);

CREATE INDEX idx_quantlab_card_features_fixture_decision
    ON quantlab_card_feature_snapshots (fixture_id, decision_at DESC);

CREATE TRIGGER quantlab_card_feature_snapshots_immutable
BEFORE UPDATE OR DELETE ON quantlab_card_feature_snapshots
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
