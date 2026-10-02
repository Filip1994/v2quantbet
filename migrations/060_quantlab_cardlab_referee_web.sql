-- CardLab V7: public-web referee profiles for top-league coverage.

CREATE TABLE quantlab_referee_web_captures (
    referee_web_capture_id TEXT PRIMARY KEY
        CHECK (referee_web_capture_id ~ '^quantlab-referee-web-capture-v1:[0-9a-f]{64}$'),
    source_name TEXT NOT NULL CHECK (source_name = 'STATBUNKER'),
    league_key TEXT NOT NULL,
    season INTEGER NOT NULL CHECK (season > 0),
    source_competition_id BIGINT NOT NULL CHECK (source_competition_id > 0),
    source_url TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    profile_count INTEGER NOT NULL CHECK (profile_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_referee_web_capture_latest
    ON quantlab_referee_web_captures (league_key, season, captured_at DESC);

CREATE TRIGGER quantlab_referee_web_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_referee_web_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_referee_web_profiles (
    referee_web_profile_id TEXT PRIMARY KEY
        CHECK (referee_web_profile_id ~ '^quantlab-referee-web-profile-v1:[0-9a-f]{64}$'),
    referee_web_capture_id TEXT NOT NULL
        REFERENCES quantlab_referee_web_captures(referee_web_capture_id),
    source_name TEXT NOT NULL CHECK (source_name = 'STATBUNKER'),
    league_key TEXT NOT NULL,
    season INTEGER NOT NULL CHECK (season > 0),
    referee_name TEXT NOT NULL,
    referee_key TEXT NOT NULL,
    matches INTEGER NOT NULL CHECK (matches > 0),
    home_cards INTEGER NOT NULL CHECK (home_cards >= 0),
    away_cards INTEGER NOT NULL CHECK (away_cards >= 0),
    yellow_cards INTEGER NOT NULL CHECK (yellow_cards >= 0),
    second_yellow_cards INTEGER NOT NULL CHECK (second_yellow_cards >= 0),
    red_cards INTEGER NOT NULL CHECK (red_cards >= 0),
    yellow_cards_per_match DOUBLE PRECISION,
    cards_per_match DOUBLE PRECISION,
    captured_at TIMESTAMPTZ NOT NULL,
    source_url TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_referee_web_profile_lookup
    ON quantlab_referee_web_profiles
    (league_key, referee_key, season DESC, captured_at DESC);

CREATE TRIGGER quantlab_referee_web_profiles_immutable
BEFORE UPDATE OR DELETE ON quantlab_referee_web_profiles
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

ALTER TABLE quantlab_card_feature_snapshots
    DROP CONSTRAINT IF EXISTS quantlab_card_feature_snapshots_feature_version_check;

ALTER TABLE quantlab_card_feature_snapshots
    ADD CONSTRAINT quantlab_card_feature_snapshots_feature_version_check
    CHECK (
        feature_version IN (
            'CARDLAB_FEATURES_V1',
            'CARDLAB_FEATURES_V2',
            'CARDLAB_FEATURES_V3',
            'CARDLAB_FEATURES_V4'
        )
    );