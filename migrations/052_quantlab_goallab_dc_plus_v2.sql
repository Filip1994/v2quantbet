-- GoalLab DC+ Pro Structural V2 successor contract.
-- V1 artifacts/picks/validations remain immutable and queryable.

ALTER TABLE quantlab_goal_model_versions
    DROP CONSTRAINT IF EXISTS quantlab_goal_model_versions_model_version_check;
ALTER TABLE quantlab_goal_model_versions
    ADD CONSTRAINT quantlab_goal_model_versions_model_version_check
    CHECK (
        model_version ~ '^DC_PLUS_PRO_STRUCTURAL_V(1|2):[0-9a-f]{64}$'
    );

ALTER TABLE quantlab_goal_model_versions
    DROP CONSTRAINT IF EXISTS quantlab_goal_model_versions_feature_version_check;
ALTER TABLE quantlab_goal_model_versions
    ADD CONSTRAINT quantlab_goal_model_versions_feature_version_check
    CHECK (
        feature_version IN (
            'GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1',
            'GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V2'
        )
    );

ALTER TABLE quantlab_goal_picks
    DROP CONSTRAINT IF EXISTS quantlab_goal_picks_pick_policy_version_check;
ALTER TABLE quantlab_goal_picks
    ADD CONSTRAINT quantlab_goal_picks_pick_policy_version_check
    CHECK (
        pick_policy_version IN (
            'GOALLAB_DC_PLUS_PICK_POLICY_V1',
            'GOALLAB_DC_PLUS_PICK_POLICY_V2'
        )
    );

ALTER TABLE quantlab_goal_picks
    DROP CONSTRAINT IF EXISTS quantlab_goal_picks_model_version_check;
ALTER TABLE quantlab_goal_picks
    ADD CONSTRAINT quantlab_goal_picks_model_version_check
    CHECK (
        model_version ~ '^DC_PLUS_PRO_STRUCTURAL_V(1|2):[0-9a-f]{64}$'
    );

ALTER TABLE quantlab_goal_model_validations
    DROP CONSTRAINT IF EXISTS quantlab_goal_model_validations_method_version_check;
ALTER TABLE quantlab_goal_model_validations
    ADD CONSTRAINT quantlab_goal_model_validations_method_version_check
    CHECK (
        method_version IN (
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V1',
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V2',
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V3',
            'GOALLAB_CHRONOLOGICAL_HOLDOUT_V4'
        )
    );
