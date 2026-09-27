-- CardLab: durable league/season referee-history bootstrap captures.
-- One league fixture payload can bootstrap several target referees at once.

CREATE TABLE quantlab_referee_history_scope_captures (
    referee_history_scope_capture_id TEXT PRIMARY KEY
        CHECK (
            referee_history_scope_capture_id
            ~ '^quantlab-referee-history-scope-v1:[0-9a-f]{64}$'
        ),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER NOT NULL CHECK (season > 0),
    window_start DATE NOT NULL,
    window_end DATE NOT NULL CHECK (window_end >= window_start),
    captured_at TIMESTAMPTZ NOT NULL,
    response_fixture_count INTEGER NOT NULL CHECK (response_fixture_count >= 0),
    referee_fixture_count INTEGER NOT NULL CHECK (referee_fixture_count >= 0),
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_referee_scope_latest
    ON quantlab_referee_history_scope_captures
    (league_id, season, captured_at DESC);

CREATE TRIGGER quantlab_referee_history_scope_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_referee_history_scope_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
