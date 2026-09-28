-- GoalLab validation V3: pooled plain-DC control keeps sparse-team matches
-- and assigns neutral latent effects to teams below the control history threshold.

ALTER TABLE quantlab_goal_model_validations
    DROP CONSTRAINT IF EXISTS quantlab_goal_model_validations_method_version_check;

ALTER TABLE quantlab_goal_model_validations
    ADD CONSTRAINT quantlab_goal_model_validations_method_version_check
    CHECK (
        method_version IN (
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V1',
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V2',
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V3'
        )
    );
