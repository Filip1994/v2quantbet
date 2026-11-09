-- OPERATOR-ONLY. Never execute as a schema migration or on every deployment.
-- User explicitly requested LOSS for the only Production Leixoes fixture.
-- Independently checked 2026-11-09: Felgueiras 1932 3-3 Leixoes,
-- corners 4-10 (14 total), making UNDER 9.5 a LOSS.
-- Evidence: https://www.zerozero.pt/live-ao-minuto/2026-11-07-fc-felgueiras-leixoes/12278383
--           https://www.totalcorner.com/h2h/felgueiras-1932-vs-leixoes
-- API-Football terminal corner counts are still unavailable: retain NULL
-- provider result/statistics IDs, do not pretend they were provider-confirmed.
-- Run only once under a transaction and an exclusive CornerLab lock.
-- Expected: exactly one inserted event; abort otherwise.

INSERT INTO quantlab_corner_settlement_events (
    corner_settlement_event_id, shadow_bet_id, fixture_id, event_kind,
    prior_event_id, result_observation_id, statistics_observation_id,
    result_classification, outcome, pnl_minor, occurred_at,
    settlement_rule_version, result_detail
)
SELECT
    'quantlab-corner-settlement-event-v1:' || encode(
        sha256(convert_to(
            'manual-loss-20261109:production-pick-v1:a14ed41856bdaf320087214e93af27e4da8c3649af5574599ff13e5149f471e9',
            'UTF8'
        )), 'hex'),
    q.shadow_bet_id, q.fixture_id, 'MANUAL_LOSS',
    NULL, NULL, NULL, NULL, 'LOSS', -q.stake_minor, CURRENT_TIMESTAMP,
    'CORNERLAB_TOTAL_CORNERS_HALF_LINE_SETTLEMENT_V1',
    jsonb_build_object(
        'manual_settlement', true,
        'manual_actor', 'user-request',
        'manual_reason', 'Operator explicitly requested LOSS for stuck Leixoes Production pick on 2026-11-09',
        'evidence_source', 'operator_verified_external_match_corners',
        'provider_confirmed', false,
        'external_result', 'Felgueiras 1932 3-3 Leixoes',
        'external_home_corner_kicks', 4,
        'external_away_corner_kicks', 10,
        'actual_total_corners', 14,
        'market_key', 'TOTAL_CORNERS',
        'selection', q.selection,
        'line', q.line,
        'odds', q.odds,
        'stake_minor', q.stake_minor,
        'production_pick_id', p.pick_id,
        'external_evidence_1', 'https://www.zerozero.pt/live-ao-minuto/2026-11-07-fc-felgueiras-leixoes/12278383',
        'external_evidence_2', 'https://www.totalcorner.com/h2h/felgueiras-1932-vs-leixoes'
    )
FROM production_funnel_picks p
JOIN quantlab_shadow_bets q ON
    p.source_universe = 'CORNERLAB'
    AND p.source_pick_id = q.shadow_bet_id
    AND p.source_fixture_id = q.fixture_id
WHERE p.pick_id = 'production-pick-v1:a14ed41856bdaf320087214e93af27e4da8c3649af5574599ff13e5149f471e9'
  AND p.source_fixture_id = 'api-football:1576526'
  AND p.home_team = 'Felgueiras 1932'
  AND p.away_team = 'Leixoes'
  AND p.kickoff_at = TIMESTAMPTZ '2026-11-07 11:00:00+00'
  AND p.market_key = 'TOTAL_CORNERS'
  AND p.selection = 'UNDER'
  AND p.line = 9.5
  AND p.stake_minor = 30000
  AND q.shadow_bet_id = 'quantlab-shadow-v1:1fb2064154eb46d03e181d81f8b5eda9dae0cb60cd22a299be66105a5404841e'
  AND q.lab = 'CORNER'
  AND q.selection = 'UNDER'
  AND q.line = 9.5
  AND q.stake_minor = 10000
  AND NOT EXISTS (
    SELECT 1 FROM quantlab_corner_settlement_events e
    WHERE e.shadow_bet_id = q.shadow_bet_id
  )
  AND NOT EXISTS (
    SELECT 1 FROM production_funnel_voids v WHERE v.pick_id = p.pick_id
  )
RETURNING corner_settlement_event_id, shadow_bet_id, fixture_id, event_kind, outcome, pnl_minor;
