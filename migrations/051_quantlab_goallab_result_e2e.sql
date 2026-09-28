-- GoalLab canonical-pick result evidence is QuantLab-owned.
-- Settlement rows must point at the exact immutable QuantLab fixture observation used
-- as the second stable terminal confirmation.

ALTER TABLE quantlab_fixture_observations
    ADD CONSTRAINT uq_quantlab_fixture_observation_fixture
    UNIQUE (fixture_observation_id, fixture_id);

ALTER TABLE quantlab_goal_pick_settlements
    ADD CONSTRAINT quantlab_goal_settlement_result_observation_fkey
    FOREIGN KEY (result_observation_id, fixture_id)
    REFERENCES quantlab_fixture_observations(fixture_observation_id, fixture_id)
    ON DELETE RESTRICT;

ALTER TABLE quantlab_goal_pick_settlements
    ADD CONSTRAINT quantlab_goal_settlement_result_observation_id_check
    CHECK (result_observation_id ~ '^quantlab-fixture-v1:[0-9a-f]{64}$');
