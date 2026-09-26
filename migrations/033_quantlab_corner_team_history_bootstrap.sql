-- CornerLab V2.1: persistent team-targeted history discovery watermark.
-- This supports market-driven bootstrap of recent team fixtures without re-polling
-- /fixtures?team=<id>&last=<n> every QuantLab cycle.

CREATE TABLE quantlab_team_history_captures (
    team_history_capture_id TEXT PRIMARY KEY
        CHECK (team_history_capture_id ~ '^quantlab-team-history-v1:[0-9a-f]{64}$'),
    team_id BIGINT NOT NULL CHECK (team_id > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    requested_last INTEGER NOT NULL CHECK (requested_last BETWEEN 3 AND 50),
    response_fixture_count INTEGER NOT NULL CHECK (response_fixture_count >= 0),
    source TEXT NOT NULL DEFAULT 'api-football:fixtures-team-last'
        CHECK (source = 'api-football:fixtures-team-last'),
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_team_history_capture_team
    ON quantlab_team_history_captures (team_id, captured_at DESC);

CREATE TRIGGER quantlab_team_history_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_team_history_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
