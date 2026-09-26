-- QuantLab broad research: persistent fixture-statistics coverage watermark.
-- Prevent repeated /fixtures/statistics calls for competitions where the provider
-- returns no usable team statistics while retaining bounded retry capability.

CREATE TABLE quantlab_statistics_captures (
    statistics_capture_id TEXT PRIMARY KEY
        CHECK (statistics_capture_id ~ '^quantlab-stats-capture-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE', 'UNAVAILABLE')),
    response_count INTEGER NOT NULL CHECK (response_count >= 0),
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_statistics_captures_fixture
    ON quantlab_statistics_captures (fixture_id, captured_at DESC);

CREATE TRIGGER quantlab_statistics_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_statistics_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
