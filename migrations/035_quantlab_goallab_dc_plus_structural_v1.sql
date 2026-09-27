-- GoalLab DC+ Pro Structural V1.
-- QuantLab-only immutable model artifacts and pre-match feature snapshots.
-- No production model, registered-pick, or bankroll state is modified.

CREATE TABLE quantlab_goal_model_versions (
    model_version TEXT PRIMARY KEY
        CHECK (model_version ~ '^DC_PLUS_PRO_STRUCTURAL_V1:[0-9a-f]{64}$'),
    trained_at TIMESTAMPTZ NOT NULL,
    training_cutoff TIMESTAMPTZ NOT NULL,
    feature_version TEXT NOT NULL
        CHECK (feature_version = 'GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1'),
    training_sample_size INTEGER NOT NULL CHECK (training_sample_size >= 0),
    history_match_count INTEGER NOT NULL CHECK (history_match_count >= training_sample_size),
    team_count INTEGER NOT NULL CHECK (team_count >= 0),
    league_count INTEGER NOT NULL CHECK (league_count >= 0),
    ridge_team NUMERIC(14,6) NOT NULL CHECK (ridge_team > 0),
    ridge_feature NUMERIC(14,6) NOT NULL CHECK (ridge_feature > 0),
    rho NUMERIC(14,9) NOT NULL,
    intercept NUMERIC(14,9) NOT NULL,
    home_advantage NUMERIC(14,9) NOT NULL,
    parameters JSONB NOT NULL,
    feature_means JSONB NOT NULL,
    feature_scales JSONB NOT NULL,
    training_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_goal_model_versions_trained
    ON quantlab_goal_model_versions (trained_at DESC, model_version DESC);

CREATE TRIGGER quantlab_goal_model_versions_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_model_versions
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_goal_feature_snapshots (
    feature_snapshot_id TEXT PRIMARY KEY
        CHECK (feature_snapshot_id ~ '^quantlab-goal-features-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    decision_at TIMESTAMPTZ NOT NULL,
    model_version TEXT NOT NULL
        REFERENCES quantlab_goal_model_versions(model_version) ON DELETE RESTRICT,
    expected_home_goals NUMERIC(14,9) NOT NULL CHECK (expected_home_goals > 0),
    expected_away_goals NUMERIC(14,9) NOT NULL CHECK (expected_away_goals > 0),
    home_history_size INTEGER NOT NULL CHECK (home_history_size >= 0),
    away_history_size INTEGER NOT NULL CHECK (away_history_size >= 0),
    feature_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_goal_feature_snapshots_fixture
    ON quantlab_goal_feature_snapshots (fixture_id, decision_at DESC);

CREATE INDEX idx_quantlab_goal_feature_snapshots_model
    ON quantlab_goal_feature_snapshots (model_version, decision_at DESC);

CREATE TRIGGER quantlab_goal_feature_snapshots_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_feature_snapshots
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
