-- QuantLab Task 001 scope correction: independent fixture universe.
-- QuantLab can now retain fixtures that production Phase-I discovery intentionally excludes.

CREATE TABLE quantlab_fixtures (
    fixture_id TEXT PRIMARY KEY,
    provider_fixture_id BIGINT NOT NULL UNIQUE CHECK (provider_fixture_id > 0),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO quantlab_fixtures (fixture_id, provider_fixture_id, first_seen_at)
SELECT
    f.fixture_id,
    f.provider_fixture_id::BIGINT,
    COALESCE(f.created_at, CURRENT_TIMESTAMP)
FROM fixtures f
WHERE f.provider = 'api-football'
  AND f.provider_fixture_id ~ '^[0-9]+$'
ON CONFLICT DO NOTHING;

CREATE TABLE quantlab_fixture_observations (
    fixture_observation_id TEXT PRIMARY KEY
        CHECK (fixture_observation_id ~ '^quantlab-fixture-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER CHECK (season IS NULL OR season > 0),
    home_team_id BIGINT CHECK (home_team_id IS NULL OR home_team_id > 0),
    away_team_id BIGINT CHECK (away_team_id IS NULL OR away_team_id > 0),
    home_team TEXT NOT NULL CHECK (length(trim(home_team)) > 0),
    away_team TEXT NOT NULL CHECK (length(trim(away_team)) > 0),
    competition_name TEXT NOT NULL CHECK (length(trim(competition_name)) > 0),
    country TEXT NOT NULL CHECK (length(trim(country)) > 0),
    competition_type TEXT NOT NULL CHECK (length(trim(competition_type)) > 0),
    kickoff_at TIMESTAMPTZ NOT NULL,
    provider_status TEXT NOT NULL CHECK (length(trim(provider_status)) > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL DEFAULT 'api-football:fixtures'
        CHECK (source = 'api-football:fixtures'),
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_fixture_observations_upcoming
    ON quantlab_fixture_observations (kickoff_at, fixture_id, captured_at DESC);
CREATE INDEX idx_quantlab_fixture_observations_fixture
    ON quantlab_fixture_observations (fixture_id, captured_at DESC);

CREATE TRIGGER quantlab_fixture_observations_immutable
BEFORE UPDATE OR DELETE ON quantlab_fixture_observations
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_fixture_discovery_shards (
    discovery_shard_id TEXT PRIMARY KEY
        CHECK (discovery_shard_id ~ '^quantlab-fixture-shard-v1:[0-9a-f]{64}$'),
    fixture_date DATE NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    fixture_count INTEGER NOT NULL CHECK (fixture_count >= 0),
    source TEXT NOT NULL DEFAULT 'api-football:fixtures-date'
        CHECK (source = 'api-football:fixtures-date')
);

CREATE INDEX idx_quantlab_fixture_discovery_date_capture
    ON quantlab_fixture_discovery_shards (fixture_date, captured_at DESC);

CREATE TRIGGER quantlab_fixture_discovery_shards_immutable
BEFORE UPDATE OR DELETE ON quantlab_fixture_discovery_shards
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

ALTER TABLE quantlab_shadow_bets
    DROP CONSTRAINT IF EXISTS quantlab_shadow_bets_fixture_id_fkey;
ALTER TABLE quantlab_shadow_bets
    ADD CONSTRAINT quantlab_shadow_bets_quantlab_fixture_fkey
    FOREIGN KEY (fixture_id) REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT;

ALTER TABLE quantlab_market_observations
    DROP CONSTRAINT IF EXISTS quantlab_market_observations_fixture_id_fkey;
ALTER TABLE quantlab_market_observations
    ADD CONSTRAINT quantlab_market_observations_quantlab_fixture_fkey
    FOREIGN KEY (fixture_id) REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT;

ALTER TABLE quantlab_fixture_context_observations
    DROP CONSTRAINT IF EXISTS quantlab_fixture_context_observations_fixture_id_fkey;
ALTER TABLE quantlab_fixture_context_observations
    ADD CONSTRAINT quantlab_fixture_context_quantlab_fixture_fkey
    FOREIGN KEY (fixture_id) REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT;

ALTER TABLE quantlab_match_statistics_observations
    DROP CONSTRAINT IF EXISTS quantlab_match_statistics_observations_fixture_id_fkey;
ALTER TABLE quantlab_match_statistics_observations
    ADD CONSTRAINT quantlab_match_statistics_quantlab_fixture_fkey
    FOREIGN KEY (fixture_id) REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT;

ALTER TABLE quantlab_card_feature_snapshots
    DROP CONSTRAINT IF EXISTS quantlab_card_feature_snapshots_fixture_id_fkey;
ALTER TABLE quantlab_card_feature_snapshots
    ADD CONSTRAINT quantlab_card_features_quantlab_fixture_fkey
    FOREIGN KEY (fixture_id) REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT;
