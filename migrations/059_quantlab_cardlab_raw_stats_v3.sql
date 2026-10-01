-- CardLab V6 raw-stat feature and decision surface.
-- Preserve frozen V1/V2 snapshots while allowing the expanded raw-statistics payload.

ALTER TABLE quantlab_card_feature_snapshots
    DROP CONSTRAINT IF EXISTS quantlab_card_feature_snapshots_feature_version_check;

ALTER TABLE quantlab_card_feature_snapshots
    ADD CONSTRAINT quantlab_card_feature_snapshots_feature_version_check
    CHECK (feature_version IN ('CARDLAB_FEATURES_V1', 'CARDLAB_FEATURES_V2', 'CARDLAB_FEATURES_V3'));

-- V6 remains single-book 1xBet for settlement authority, but replaces the Poisson
-- value gate with a price-independent raw-stat consensus policy. Probability/EV
-- columns stay populated only because the existing immutable decision ledger uses
-- them as diagnostic fields.
ALTER TABLE quantlab_context_market_decisions
    DROP CONSTRAINT IF EXISTS quantlab_context_market_decisions_pick_evidence_v2_check;

ALTER TABLE quantlab_context_market_decisions
    ADD CONSTRAINT quantlab_context_market_decisions_pick_evidence_v3_check
    CHECK (
        decision = 'PASS'
        OR (
            bookmaker_id IS NOT NULL
            AND provider_bet_id IS NOT NULL
            AND market_key IS NOT NULL
            AND selection IN ('OVER', 'UNDER')
            AND line IS NOT NULL
            AND selected_observation_id IS NOT NULL
            AND companion_observation_id IS NOT NULL
            AND quote_observed_at IS NOT NULL
            AND odds IS NOT NULL
            AND companion_odds IS NOT NULL
            AND market_probability IS NOT NULL
            AND model_probability IS NOT NULL
            AND edge IS NOT NULL
            AND expected_value IS NOT NULL
            AND (
                lab = 'CORNER'
                OR (
                    lab = 'CARD'
                    AND (
                        (
                            (
                                policy_version LIKE 'CARDLAB_1XBET_POISSON_POLICY_%'
                                OR policy_version LIKE 'CARDLAB_RAW_STATS_POLICY_%'
                            )
                            AND bookmaker_id = 11
                            AND reference_bookmaker_id IS NULL
                            AND reference_bookmaker_name IS NULL
                            AND reference_observation_id IS NULL
                            AND reference_companion_observation_id IS NULL
                            AND reference_quote_observed_at IS NULL
                            AND reference_odds IS NULL
                            AND reference_companion_odds IS NULL
                        )
                        OR (
                            policy_version NOT LIKE 'CARDLAB_1XBET_POISSON_POLICY_%'
                            AND policy_version NOT LIKE 'CARDLAB_RAW_STATS_POLICY_%'
                            AND reference_bookmaker_id IS NOT NULL
                            AND reference_bookmaker_name IS NOT NULL
                            AND reference_bookmaker_id <> bookmaker_id
                            AND reference_observation_id IS NOT NULL
                            AND reference_companion_observation_id IS NOT NULL
                            AND reference_quote_observed_at IS NOT NULL
                            AND reference_odds IS NOT NULL
                            AND reference_companion_odds IS NOT NULL
                        )
                    )
                )
            )
        )
    );
