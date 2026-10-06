-- Manual settlement of two source picks whose provider evidence was durable but the
-- automatic finality paths did not produce a consumable settlement.
--
-- 1) SAT Moreno 2-2 Deportivo Metalurgico (api-football:1642031)
--    API-Football returned PEN with goals/fulltime=2-2 but omitted the penalty breakdown.
--    The strict V1 normalizer therefore stored INVALID_TERMINAL. Preserve that immutable
--    provider observation and append an explicit manual result override.
--
-- 2) Platense 2-1 Municipal Limeno (api-football:1600621)
--    QuantLab retained one authoritative FT snapshot, but GoalLab requires two terminal
--    snapshots 15 minutes apart. Append the GoalLab settlement from the retained FT fact.
--
-- Both Production funnel rows remain SKIPPED. This migration settles source outcomes only;
-- it does not create PLAYED exposure or mutate operator state.

ALTER TABLE fixture_result_observations
    DROP CONSTRAINT fixture_result_observations_normalizer_version_check;

ALTER TABLE fixture_result_observations
    ADD CONSTRAINT fixture_result_observations_normalizer_version_check
    CHECK (normalizer_version IN (
        'API_FOOTBALL_SETTLEMENT_RESULT_V1',
        'MANUAL_RESULT_OVERRIDE_V1'
    ));

WITH source AS (
    SELECT *
    FROM fixture_result_observations
    WHERE result_observation_id =
        'fixture-result-observation-v1:a29a86f6aa90a41760a3acf59da7fa17c04804d3ddb32e6be9ba6856f3a2cecd'
      AND fixture_id = 'api-football:1642031'
      AND provider_status = 'PEN'
      AND goals_home = 2
      AND goals_away = 2
      AND fulltime_home = 2
      AND fulltime_away = 2
)
INSERT INTO fixture_result_observations (
    result_observation_id, fixture_id, provider, provider_fixture_id, provider_status,
    provider_kickoff_at, provider_home_team_id, provider_away_team_id,
    goals_home, goals_away, fulltime_home, fulltime_away,
    extratime_home, extratime_away, penalty_home, penalty_away,
    regulation_home_goals, regulation_away_goals, result_classification,
    settlement_fingerprint, normalizer_version, provider_record_sha256,
    provider_record, first_acquired_at
)
SELECT
    'fixture-result-observation-v1:a0ed6df34fb0db689a3851d9368235d989834a74f6b0f49b9d7181ef898a336f',
    fixture_id, provider, provider_fixture_id, provider_status, provider_kickoff_at,
    provider_home_team_id, provider_away_team_id,
    goals_home, goals_away, fulltime_home, fulltime_away,
    extratime_home, extratime_away, penalty_home, penalty_away,
    2, 2, 'PLAYED_SETTLEABLE',
    'result-settlement-v1:a36b11cc5624df619bab108aff0a35f29ea20bc26438eb7fac2652f211c6556e',
    'MANUAL_RESULT_OVERRIDE_V1',
    '6e766a66a7c19c9bd9b432b2b7e8893578391d07156737cda704013bc47b5b0f',
    provider_record || jsonb_build_object(
        'quantbet_manual_settlement',
        jsonb_build_object(
            'actor', 'operator',
            'reason',
            'Manual settlement of provider PEN record with omitted penalty breakdown; latest stored API-Football goals/fulltime are 2-2.',
            'source_result_observation_id',
            'fixture-result-observation-v1:a29a86f6aa90a41760a3acf59da7fa17c04804d3ddb32e6be9ba6856f3a2cecd'
        )
    ),
    CURRENT_TIMESTAMP
FROM source
ON CONFLICT DO NOTHING;

UPDATE fixture_result_acquisition_states
SET
    phase = 'COMPLETE',
    current_observation_id =
        'fixture-result-observation-v1:a0ed6df34fb0db689a3851d9368235d989834a74f6b0f49b9d7181ef898a336f',
    candidate_observation_id = NULL,
    candidate_settlement_fingerprint = NULL,
    candidate_first_seen_at = NULL,
    candidate_confirmation_count = 0,
    next_check_at = CURRENT_TIMESTAMP,
    lease_expires_at = NULL,
    last_checked_at = CURRENT_TIMESTAMP,
    correction_required = FALSE,
    contradicting_observation_id = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE fixture_id = 'api-football:1642031'
  AND current_observation_id =
      'fixture-result-observation-v1:a29a86f6aa90a41760a3acf59da7fa17c04804d3ddb32e6be9ba6856f3a2cecd'
  AND EXISTS (
      SELECT 1
      FROM fixture_result_observations
      WHERE result_observation_id =
          'fixture-result-observation-v1:a0ed6df34fb0db689a3851d9368235d989834a74f6b0f49b9d7181ef898a336f'
        AND fixture_id = 'api-football:1642031'
  );

INSERT INTO quantlab_goal_pick_settlements (
    goal_pick_settlement_id, goal_pick_id, fixture_id, result_observation_id,
    result_classification, regulation_home_goals, regulation_away_goals,
    outcome, pnl_minor, settled_at, settlement_rule_version, result_detail
)
SELECT
    'quantlab-goal-settlement-v1:42704bf19da52ff267a1e3e3fed85bfb1155fbd56344b1590aa8fe2215ff8983',
    gp.goal_pick_id, gp.fixture_id, q.fixture_observation_id,
    'PLAYED_SETTLEABLE', 2, 1, 'WIN',
    round(gp.stake_minor * (gp.odds - 1))::bigint,
    CURRENT_TIMESTAMP, 'GOALLAB_SETTLEMENT_V1',
    jsonb_build_object(
        'market_key', gp.market_key,
        'selection', gp.selection,
        'odds', gp.odds,
        'stake_minor', gp.stake_minor,
        'provider_status', q.provider_status,
        'regulation_home_goals', 2,
        'regulation_away_goals', 1,
        'semantic', 'regulation_total_goals=3',
        'result_confirmation_count', 1,
        'manual_settlement', true,
        'manual_reason',
            'One retained QuantLab FT provider snapshot; operator requested settlement from durable API-Football result evidence.',
        'result_source_observation_id', q.fixture_observation_id
    )
FROM quantlab_goal_picks gp
JOIN quantlab_fixture_observations q ON q.fixture_id = gp.fixture_id
WHERE gp.goal_pick_id =
      'quantlab-goal-pick-v1:b80253e4857e881140e1a2feec4d31e913644c253c7b9631cdb0be77d37eb368'
  AND gp.fixture_id = 'api-football:1600621'
  AND gp.market_key = 'OU_25'
  AND gp.selection = 'OVER'
  AND gp.line = 2.5
  AND gp.odds = 2.10
  AND gp.stake_minor = 10000
  AND q.fixture_observation_id =
      'quantlab-fixture-v1:dd5b6951d8c397d5f8b38226656b0d962666d8827dcf331f06c3435cb9d3ac0f'
  AND q.provider_status = 'FT'
  AND (q.raw_payload -> 'goals' ->> 'home')::integer = 2
  AND (q.raw_payload -> 'goals' ->> 'away')::integer = 1
ON CONFLICT DO NOTHING;
