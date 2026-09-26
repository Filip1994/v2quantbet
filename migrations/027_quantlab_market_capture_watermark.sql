-- QuantLab API-discipline correction: persist successful market captures even when
-- API-Football returns no usable Bet365/1xBet markets. This prevents restart/cycle
-- loops from spending another request merely because zero market rows were stored.

CREATE TABLE quantlab_market_captures (
    market_capture_id TEXT PRIMARY KEY
        CHECK (market_capture_id ~ '^quantlab-market-capture-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    raw_observation_count INTEGER NOT NULL CHECK (raw_observation_count >= 0),
    stored_observation_count INTEGER NOT NULL CHECK (stored_observation_count >= 0),
    allowed_labs JSONB NOT NULL,
    source TEXT NOT NULL DEFAULT 'api-football:odds'
        CHECK (source = 'api-football:odds')
);

CREATE INDEX idx_quantlab_market_captures_fixture
    ON quantlab_market_captures (fixture_id, captured_at DESC);

CREATE TRIGGER quantlab_market_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_market_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
