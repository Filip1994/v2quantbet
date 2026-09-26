-- QuantLab bootstrap follow-up.
-- Seed a bounded current fixture snapshot from already-persisted production fixture facts
-- without making provider requests. This is a one-time bridge only; ongoing QuantLab
-- fixture discovery remains the independent global API-Football date-shard pipeline.

ALTER TABLE quantlab_fixture_observations
    DROP CONSTRAINT IF EXISTS quantlab_fixture_observations_source_check;

ALTER TABLE quantlab_fixture_observations
    ADD CONSTRAINT quantlab_fixture_observations_source_check CHECK (
        source IN ('api-football:fixtures', 'production-fixture-bootstrap')
    );

INSERT INTO quantlab_fixtures (fixture_id, provider_fixture_id, first_seen_at)
SELECT
    f.fixture_id,
    f.provider_fixture_id::BIGINT,
    f.created_at
FROM fixtures f
JOIN LATERAL (
    SELECT o.kickoff_at
    FROM fixture_observations o
    WHERE o.fixture_id = f.fixture_id
    ORDER BY o.observed_at DESC, o.fixture_observation_id DESC
    LIMIT 1
) latest ON TRUE
WHERE f.provider = 'api-football'
  AND f.provider_fixture_id ~ '^[1-9][0-9]*$'
  AND latest.kickoff_at >= CURRENT_TIMESTAMP - INTERVAL '1 day'
  AND latest.kickoff_at < CURRENT_TIMESTAMP + INTERVAL '3 days'
ON CONFLICT DO NOTHING;

WITH latest AS (
    SELECT DISTINCT ON (o.fixture_id)
        f.fixture_id,
        f.provider_fixture_id::BIGINT AS provider_fixture_id,
        f.league_id,
        f.season,
        f.provider_home_team_id AS home_team_id,
        f.provider_away_team_id AS away_team_id,
        o.home_team,
        o.away_team,
        o.competition_name,
        o.country,
        o.competition_type,
        o.kickoff_at,
        o.provider_status,
        o.observed_at,
        o.persisted_at,
        o.fixture_observation_id AS production_fixture_observation_id,
        o.source AS production_source
    FROM fixture_observations o
    JOIN fixtures f ON f.fixture_id = o.fixture_id
    WHERE f.provider = 'api-football'
      AND o.kickoff_at >= CURRENT_TIMESTAMP - INTERVAL '1 day'
      AND o.kickoff_at < CURRENT_TIMESTAMP + INTERVAL '3 days'
    ORDER BY o.fixture_id, o.observed_at DESC, o.fixture_observation_id DESC
)
INSERT INTO quantlab_fixture_observations (
    fixture_observation_id,
    fixture_id,
    provider_fixture_id,
    league_id,
    season,
    home_team_id,
    away_team_id,
    home_team,
    away_team,
    competition_name,
    country,
    competition_type,
    kickoff_at,
    provider_status,
    captured_at,
    source,
    raw_payload
)
SELECT
    'quantlab-fixture-v1:' ||
        substring(
            latest.production_fixture_observation_id
            FROM char_length('fixture-observation-v1:') + 1
        ),
    latest.fixture_id,
    latest.provider_fixture_id,
    latest.league_id,
    latest.season,
    latest.home_team_id,
    latest.away_team_id,
    latest.home_team,
    latest.away_team,
    latest.competition_name,
    latest.country,
    latest.competition_type,
    latest.kickoff_at,
    latest.provider_status,
    latest.observed_at,
    'production-fixture-bootstrap',
    jsonb_build_object(
        'bootstrap_source', 'production_fixture_observations',
        'production_fixture_observation_id', latest.production_fixture_observation_id,
        'production_source', latest.production_source,
        'production_observed_at', latest.observed_at,
        'production_persisted_at', latest.persisted_at
    )
FROM latest
JOIN quantlab_fixtures qf ON qf.fixture_id = latest.fixture_id
WHERE NOT EXISTS (
    SELECT 1
    FROM quantlab_fixture_observations existing
    WHERE existing.fixture_id = latest.fixture_id
)
ON CONFLICT DO NOTHING;
