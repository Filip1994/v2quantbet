-- GoalLab manager/coach context acquisition.
-- Team-level snapshots are append-only and timestamped for future leakage-safe training.

CREATE TABLE quantlab_goal_coach_captures (
    coach_capture_id TEXT PRIMARY KEY
        CHECK (coach_capture_id ~ '^quantlab-goal-coach-v1:[0-9a-f]{64}$'),
    team_id BIGINT NOT NULL CHECK (team_id > 0),
    available_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE', 'UNAVAILABLE')),
    response_item_count INTEGER NOT NULL CHECK (response_item_count >= 0),
    reason TEXT,
    source TEXT NOT NULL DEFAULT 'api-football:coachs'
        CHECK (source = 'api-football:coachs'),
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_goal_coach_team_available
    ON quantlab_goal_coach_captures (team_id, available_at DESC);

CREATE TRIGGER quantlab_goal_coach_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_coach_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
