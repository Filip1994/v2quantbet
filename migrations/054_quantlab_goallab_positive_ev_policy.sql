-- GoalLab V4 pick policy: positive EV is the only hard value gate.
-- Historical pick-policy versions remain immutable and queryable.

ALTER TABLE quantlab_goal_picks
    DROP CONSTRAINT IF EXISTS quantlab_goal_picks_pick_policy_version_check;
ALTER TABLE quantlab_goal_picks
    ADD CONSTRAINT quantlab_goal_picks_pick_policy_version_check
    CHECK (pick_policy_version IN (
        'GOALLAB_DC_PLUS_PICK_POLICY_V1',
        'GOALLAB_DC_PLUS_PICK_POLICY_V2',
        'GOALLAB_DC_PLUS_PICK_POLICY_V3',
        'GOALLAB_DC_PLUS_PICK_POLICY_V4'
    ));
