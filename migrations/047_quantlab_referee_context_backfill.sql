-- CardLab: recover referee history from already-captured team fixture payloads.
-- No provider calls are required. Availability is conservatively set to the original
-- team-history capture time so historical features remain leakage-safe.

INSERT INTO quantlab_fixture_context_observations (
    context_observation_id,
    fixture_id,
    provider_fixture_id,
    referee,
    provider_status,
    kickoff_at,
    provider_updated_at,
    available_at,
    source,
    raw_payload
)
SELECT
    'quantlab-context-v1:' || encode(
        sha256(
            convert_to(
                f.fixture_id || ':' ||
                h.captured_at::TEXT || ':' ||
                COALESCE(NULLIF(BTRIM(record #>> '{fixture,referee}'), ''), 'NO_REFEREE') ||
                ':team-history-context',
                'UTF8'
            )
        ),
        'hex'
    ),
    f.fixture_id,
    f.provider_fixture_id,
    NULLIF(BTRIM(record #>> '{fixture,referee}'), ''),
    COALESCE(
        NULLIF(BTRIM(record #>> '{fixture,status,short}'), ''),
        NULLIF(BTRIM(record #>> '{fixture,status,long}'), ''),
        'UNKNOWN'
    ),
    (record #>> '{fixture,date}')::TIMESTAMPTZ,
    NULLIF(
        COALESCE(record ->> 'update', record #>> '{fixture,update}'),
        ''
    )::TIMESTAMPTZ,
    h.captured_at,
    'api-football',
    record
FROM quantlab_team_history_captures h
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(h.raw_payload -> 'response') = 'array'
        THEN h.raw_payload -> 'response'
        ELSE '[]'::JSONB
    END
) AS record
JOIN quantlab_fixtures f
    ON (record #>> '{fixture,id}') ~ '^[0-9]+$'
   AND f.provider_fixture_id = (record #>> '{fixture,id}')::BIGINT
WHERE NULLIF(BTRIM(record #>> '{fixture,date}'), '') IS NOT NULL
ON CONFLICT DO NOTHING;
