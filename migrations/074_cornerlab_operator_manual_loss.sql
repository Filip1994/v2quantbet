-- Explicit audited manual LOSS for corner picks with externally verified outcome
-- when the provider terminal fixture/statistics observations have stalled.
-- No invented fixture_result_observations or quantlab statistics are inserted.
-- This migration changes schema only. It does not settle historical picks.

ALTER TABLE quantlab_corner_settlement_events
    DROP CONSTRAINT quantlab_corner_settlement_events_event_kind_check,
    ADD CONSTRAINT quantlab_corner_settlement_events_event_kind_check
        CHECK (event_kind IN (
            'NORMAL', 'CORRECTION', 'REVERSAL', 'LEGACY_BACKFILL',
            'MANUAL_VOID', 'MANUAL_LOSS'
        ));

ALTER TABLE quantlab_corner_settlement_events
    DROP CONSTRAINT quantlab_corner_settlement_events_check,
    ADD CONSTRAINT quantlab_corner_settlement_events_check
        CHECK (
            (event_kind = 'NORMAL'
                AND prior_event_id IS NULL AND result_observation_id IS NOT NULL
                AND result_classification IS NOT NULL AND outcome IS NOT NULL
                AND pnl_minor IS NOT NULL)
            OR (event_kind = 'LEGACY_BACKFILL'
                AND prior_event_id IS NULL AND result_classification IS NOT NULL
                AND outcome IS NOT NULL AND pnl_minor IS NOT NULL)
            OR (event_kind = 'CORRECTION'
                AND prior_event_id IS NOT NULL AND result_observation_id IS NOT NULL
                AND result_classification IS NOT NULL AND outcome IS NOT NULL
                AND pnl_minor IS NOT NULL)
            OR (event_kind = 'REVERSAL'
                AND prior_event_id IS NOT NULL AND outcome IS NULL AND pnl_minor IS NULL)
            OR (event_kind = 'MANUAL_VOID'
                AND prior_event_id IS NULL AND result_observation_id IS NULL
                AND statistics_observation_id IS NULL AND result_classification IS NULL
                AND outcome = 'VOID' AND pnl_minor = 0)
            OR (event_kind = 'MANUAL_LOSS'
                AND prior_event_id IS NULL AND result_observation_id IS NULL
                AND statistics_observation_id IS NULL AND result_classification IS NULL
                AND outcome = 'LOSS' AND pnl_minor < 0
                AND result_detail ->> 'evidence_source' = 'operator_verified_external_match_corners'
                AND result_detail ->> 'manual_settlement' = 'true')
        );

-- One initial event per pick regardless of automatic or manual path.
DROP INDEX uq_quantlab_corner_one_initial_settlement;
CREATE UNIQUE INDEX uq_quantlab_corner_one_initial_settlement
    ON quantlab_corner_settlement_events (shadow_bet_id)
    WHERE event_kind IN ('NORMAL', 'LEGACY_BACKFILL', 'MANUAL_VOID', 'MANUAL_LOSS');
