-- Operational GoalLab result-poll fairness. No settlement or financial facts change.
-- An unanswered/filtered provider request must not indefinitely monopolize the
-- first 25 unsettled GoalLab candidates.
CREATE TABLE quantlab_goal_result_poll_attempts (
    fixture_id TEXT PRIMARY KEY
        REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    last_attempt_at TIMESTAMPTZ NOT NULL,
    attempt_count BIGINT NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
    last_outcome TEXT NOT NULL
        CHECK (last_outcome IN ('CAPTURED', 'NO_MATCH', 'ERROR'))
);

CREATE INDEX idx_quantlab_goal_result_poll_attempt_time
    ON quantlab_goal_result_poll_attempts (last_attempt_at);
