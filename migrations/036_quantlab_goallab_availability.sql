-- GoalLab availability acquisition: richer league coverage and timestamped injuries.
-- QuantLab-only append-only state. Production picks/bankroll remain untouched.

ALTER TABLE quantlab_league_coverage_captures
    ADD COLUMN statistics_players BOOLEAN,
    ADD COLUMN lineups BOOLEAN,
    ADD COLUMN standings BOOLEAN,
    ADD COLUMN players BOOLEAN,
    ADD COLUMN injuries BOOLEAN,
    ADD COLUMN predictions BOOLEAN,
    ADD COLUMN odds BOOLEAN;

CREATE TABLE quantlab_goal_injury_captures (
    injury_capture_id TEXT PRIMARY KEY
        CHECK (injury_capture_id ~ '^quantlab-goal-injuries-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    available_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE', 'UNAVAILABLE')),
    response_item_count INTEGER NOT NULL CHECK (response_item_count >= 0),
    reason TEXT,
    source TEXT NOT NULL CHECK (
        source IN ('api-football:injuries', 'api-football:leagues')
    ),
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_goal_injury_fixture_available
    ON quantlab_goal_injury_captures (fixture_id, available_at DESC);

CREATE TRIGGER quantlab_goal_injury_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_injury_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
