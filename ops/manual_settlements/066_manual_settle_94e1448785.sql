-- OPERATOR-ONLY ARCHIVE: DO NOT EXECUTE DURING AUTOMATED MIGRATIONS.
-- Original production-only settlement procedure, preserved verbatim below.
-- This script requires terminal provider evidence and operator authorization.
-- It must not be replayed for routine CI, schema creation, or service deployment.
-- Existing production history is preserved without re-executing this script.

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
--
-- Safety: bind the manual score to a real terminal QuantLab provider observation.
-- If no FT/AET/PEN observation exists, abort rather than invent provider evidence.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM quantlab_fixture_observations q
        WHERE q.fixture_id = 'api-football:1644168'
          AND q.provider_status IN ('FT', 'AET', 'PEN')
    ) THEN
        RAISE EXCEPTION
            'Cannot manually settle 94e1448785: no terminal QuantLab provider observation for api-football:1644168';
    END IF;
END
$$;

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
    q.fixture_observation_id,
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
        'provider_status', q.provider_status,
        'provider_observation_id', q.fixture_observation_id,
        'provider_observed_goals', q.raw_payload -> 'goals',
        'regulation_home_goals', 1,
        'regulation_away_goals', 1,
        'semantic', 'regulation_total_goals=2',
        'manual_settlement', true,
        'manual_reason', 'Operator confirmed final score 1-1 for Production pick suffix 94e1448785.',
        'evidence_source', 'operator_confirmation_bound_to_terminal_provider_observation',
        'production_pick_id',
            'production-pick-v1:31e53b49712a19ef6799f0bfd1f8d53b86206388eb88ac46fc2eaa94e1448785'
    )
FROM quantlab_goal_picks gp
JOIN LATERAL (
    SELECT
        qo.fixture_observation_id,
        qo.provider_status,
        qo.raw_payload
    FROM quantlab_fixture_observations qo
    WHERE qo.fixture_id = gp.fixture_id
      AND qo.provider_status IN ('FT', 'AET', 'PEN')
    ORDER BY qo.captured_at DESC, qo.fixture_observation_id DESC
    LIMIT 1
) q ON TRUE
WHERE gp.goal_pick_id =
      'quantlab-goal-pick-v1:97ae2968e649f03090c22fabfea54b691394a057d3f38dacdb81f40fbfbec3a8'
  AND gp.fixture_id = 'api-football:1644168'
  AND gp.market_key = 'OU_25'
  AND gp.selection = 'OVER'
  AND gp.line = 2.5
  AND gp.odds = 2.05
ON CONFLICT DO NOTHING;
