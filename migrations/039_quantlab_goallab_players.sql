-- GoalLab historical per-player match performance acquisition.
-- Completed-match player facts feed the separate player-form / late-lineup layer.

CREATE TABLE quantlab_goal_player_captures (
    player_capture_id TEXT PRIMARY KEY
        CHECK (player_capture_id ~ '^quantlab-goal-players-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    available_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE', 'UNAVAILABLE')),
    response_team_count INTEGER NOT NULL CHECK (response_team_count >= 0),
    reason TEXT,
    source TEXT NOT NULL CHECK (
        source IN ('api-football:fixtures/players', 'api-football:leagues')
    ),
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_goal_player_fixture_available
    ON quantlab_goal_player_captures (fixture_id, available_at DESC);

CREATE TRIGGER quantlab_goal_player_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_player_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
