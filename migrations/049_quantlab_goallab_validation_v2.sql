-- GoalLab validation V2: allow a second immutable validation method per model artifact.
-- V1 rows remain immutable and queryable; V2 may add a pooled stable-team plain-DC fallback.

ALTER TABLE quantlab_goal_model_validations
    DROP CONSTRAINT IF EXISTS quantlab_goal_model_validations_method_version_check;

ALTER TABLE quantlab_goal_model_validations
    ADD CONSTRAINT quantlab_goal_model_validations_method_version_check
    CHECK (
        method_version IN (
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V1',
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V2'
        )
    );
