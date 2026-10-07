-- Manual GoalLab settlement requested by operator for Production pick suffix 94e1448785.
--
-- Production pick:
--   production-pick-v1:31e53b49712a19ef6799f0bfd1f8d53b86206388eb88ac46fc2eaa94e1448785
-- Source GoalLab pick:
--   quantlab-goal-pick-v1:97ae2968e649f03090c22fabfea54b691394a057d3f38dacdb81f40fbfbec3a8
-- Fixture:
--   api-football:1644168 Scarborough Athletic - Macclesfield
--
-- Operator-confirmed final score: 1-1.
-- Market: OU_25 OVER 2.5 @ 2.05 -> LOSS.
--
-- This appends the source settlement only. It does not mutate the Production
-- PLAYED/SKIPPED operator state.

INSERT INTO quantlab_goal_pick_settlements (
    goal_pick_settlement_id,
    goal_pick_id,
    fixture_id,
    result_observation_id,
    result_classification,
    regulation_home_goals,
    regulation_away_goals,
    outcome,
    pnl_minor,
    settled_at,
    settlement_rule_version,
    result_detail
)
SELECT
    'quantlab-goal-settlement-v1:97ae2968e649f03090c22fabfea54b691394a057d3f38dacdb81f40fbfbec3a8',
    gp.goal_pick_id,
    gp.fixture_id,
    'manual-result-v1:production-pick-94e1448785:user-confirmed-1-1',
    'PLAYED_SETTLEABLE',
    1,
    1,
    'LOSS',
    -gp.stake_minor,
    CURRENT_TIMESTAMP,
    'GOALLAB_SETTLEMENT_V1',
    jsonb_build_object(
        'market_key', gp.market_key,
        'selection', gp.selection,
        'line', gp.line,
        'odds', gp.odds,
        'stake_minor', gp.stake_minor,
        'regulation_home_goals', 1,
        'regulation_away_goals', 1,
        'semantic', 'regulation_total_goals=2',
        'manual_settlement', true,
        'manual_reason', 'Operator confirmed final score 1-1 for Production pick suffix 94e1448785.',
        'evidence_source', 'operator_confirmation',
        'production_pick_id',
            'production-pick-v1:31e53b49712a19ef6799f0bfd1f8d53b86206388eb88ac46fc2eaa94e1448785'
    )
FROM quantlab_goal_picks gp
WHERE gp.goal_pick_id =
      'quantlab-goal-pick-v1:97ae2968e649f03090c22fabfea54b691394a057d3f38dacdb81f40fbfbec3a8'
  AND gp.fixture_id = 'api-football:1644168'
  AND gp.market_key = 'OU_25'
  AND gp.selection = 'OVER'
  AND gp.line = 2.5
  AND gp.odds = 2.05
ON CONFLICT DO NOTHING;
