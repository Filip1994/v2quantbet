-- An operator can void a postponed pick without rewriting provider evidence.
-- The event and refund remain append-only, and the manual path records zero
-- provider confirmations instead of pretending PST is a terminal result.
ALTER TABLE pick_settlement_events
    DROP CONSTRAINT pick_settlement_events_event_kind_check,
    DROP CONSTRAINT pick_settlement_events_settlement_rule_version_check,
    DROP CONSTRAINT pick_settlement_events_confirmation_count_check,
    DROP CONSTRAINT pick_settlement_events_check1;

ALTER TABLE pick_settlement_events
    ADD CONSTRAINT pick_settlement_events_event_kind_check
        CHECK (event_kind IN ('NORMAL', 'MANUAL_VOID', 'CORRECTION', 'REVERSAL')),
    ADD CONSTRAINT pick_settlement_events_settlement_rule_version_check
        CHECK (settlement_rule_version IN (
            'SETTLEMENT_OU25_BTTS_REGULATION_V1', 'MANUAL_POSTPONEMENT_VOID_V1'
        )),
    ADD CONSTRAINT pick_settlement_events_confirmation_count_check
        CHECK (confirmation_count >= 0),
    ADD CONSTRAINT pick_settlement_events_check1 CHECK (
        (event_kind = 'NORMAL' AND prior_event_id IS NULL AND outcome IS NOT NULL
            AND gross_return_minor IS NOT NULL AND realized_pnl_minor IS NOT NULL
            AND confirmation_count >= 2
            AND settlement_rule_version = 'SETTLEMENT_OU25_BTTS_REGULATION_V1'
            AND reason IS NULL AND actor IS NULL)
        OR
        (event_kind = 'MANUAL_VOID' AND prior_event_id IS NULL AND outcome = 'VOID'
            AND gross_return_minor = stake_minor AND realized_pnl_minor = 0
            AND ledger_delta_minor = stake_minor AND confirmation_count = 0
            AND settlement_rule_version = 'MANUAL_POSTPONEMENT_VOID_V1'
            AND reason IS NOT NULL AND actor IS NOT NULL
            AND length(trim(reason)) > 0 AND length(trim(actor)) > 0)
        OR
        (event_kind = 'CORRECTION' AND prior_event_id IS NOT NULL AND outcome IS NOT NULL
            AND gross_return_minor IS NOT NULL AND realized_pnl_minor IS NOT NULL
            AND confirmation_count >= 2
            AND reason IS NOT NULL AND actor IS NOT NULL)
        OR
        (event_kind = 'REVERSAL' AND prior_event_id IS NOT NULL AND outcome IS NULL
            AND gross_return_minor IS NULL AND realized_pnl_minor IS NULL
            AND confirmation_count >= 2
            AND reason IS NOT NULL AND actor IS NOT NULL)
    );

CREATE UNIQUE INDEX uq_pick_one_initial_settlement
    ON pick_settlement_events (pick_id)
    WHERE event_kind IN ('NORMAL', 'MANUAL_VOID');
