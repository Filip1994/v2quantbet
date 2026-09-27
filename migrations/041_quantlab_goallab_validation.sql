-- GoalLab DC+ validation ledger.
-- Records chronological holdout/leakage evidence for each immutable model artifact.

CREATE TABLE quantlab_goal_model_validations (
    validation_id TEXT PRIMARY KEY
        CHECK (validation_id ~ '^quantlab-goal-validation-v1:[0-9a-f]{64}$'),
    model_version TEXT NOT NULL
        REFERENCES quantlab_goal_model_versions(model_version) ON DELETE RESTRICT,
    evaluated_at TIMESTAMPTZ NOT NULL,
    method_version TEXT NOT NULL
        CHECK (method_version = 'GOALLAB_CHRONOLOGICAL_HOLDOUT_V1'),
    status TEXT NOT NULL CHECK (
        status IN ('OK', 'INSUFFICIENT_HISTORY', 'FIT_FAILED', 'CONTROL_FIT_FAILED')
    ),
    train_start_at TIMESTAMPTZ,
    train_end_at TIMESTAMPTZ,
    holdout_start_at TIMESTAMPTZ,
    holdout_end_at TIMESTAMPTZ,
    train_sample_size INTEGER NOT NULL CHECK (train_sample_size >= 0),
    holdout_sample_size INTEGER NOT NULL CHECK (holdout_sample_size >= 0),
    common_evaluation_size INTEGER NOT NULL CHECK (common_evaluation_size >= 0),
    dc_plus_metrics JSONB NOT NULL,
    control_metrics JSONB NOT NULL,
    comparison JSONB NOT NULL,
    leakage_audit JSONB NOT NULL,
    contract_snapshot JSONB NOT NULL,
    authority_review_status TEXT NOT NULL CHECK (
        authority_review_status IN ('NOT_READY', 'READY_FOR_MANUAL_REVIEW')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (model_version, method_version)
);

CREATE INDEX idx_quantlab_goal_validations_model
    ON quantlab_goal_model_validations (model_version, evaluated_at DESC);

CREATE TRIGGER quantlab_goal_model_validations_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_model_validations
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
