-- Support audited operator-only VOID events for postponed CornerLab picks.
-- A manual VOID is independent of provider result classification. Never fabricate
-- a terminal provider observation: both observation ids and classification are NULL.
-- Source shadow picks stay immutable; reports project the latest settlement event.

ALTER TABLE quantlab_corner_settlement_events
    DROP CONSTRAINT quantlab_corner_settlement_events_event_kind_check,
    ADD CONSTRAINT quantlab_corner_settlement_events_event_kind_check
        CHECK (event_kind IN ('NORMAL', 'CORRECTION', 'REVERSAL',
                             'LEGACY_BACKFILL', 'MANUAL_VOID'));

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
        );

-- A manual VOID is an initial terminal settlement, not a legacy backfill or
-- provider-confirmed result; prevent another initial event for the same pick.
DROP INDEX uq_quantlab_corner_one_initial_settlement;
CREATE UNIQUE INDEX uq_quantlab_corner_one_initial_settlement
    ON quantlab_corner_settlement_events(shadow_bet_id)
    WHERE event_kind IN ('NORMAL', 'LEGACY_BACKFILL', 'MANUAL_VOID');
