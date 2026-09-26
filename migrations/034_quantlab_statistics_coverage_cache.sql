-- CornerLab V2.3: persistent API-Football league/season fixture-statistics coverage cache.
-- A false statistics_fixtures flag is a provider-declared coverage miss and prevents
-- wasteful per-fixture /fixtures/statistics calls until the cache expires.
-- NULL remains UNKNOWN and never fabricates unsupported coverage.

CREATE TABLE quantlab_league_coverage_captures (
    coverage_capture_id TEXT PRIMARY KEY
        CHECK (coverage_capture_id ~ '^quantlab-league-coverage-v1:[0-9a-f]{64}$'),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER NOT NULL CHECK (season > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    statistics_fixtures_supported BOOLEAN,
    response_item_count INTEGER NOT NULL CHECK (response_item_count >= 0),
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_league_coverage_lookup
    ON quantlab_league_coverage_captures (league_id, season, captured_at DESC);

CREATE TRIGGER quantlab_league_coverage_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_league_coverage_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
