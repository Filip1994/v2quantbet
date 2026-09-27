-- CardLab V4: single-book 1xBet decisions no longer require cross-book evidence.

ALTER TABLE quantlab_context_market_decisions
    DROP CONSTRAINT IF EXISTS quantlab_context_market_decisions_pick_evidence_check;

ALTER TABLE quantlab_context_market_decisions
    ADD CONSTRAINT quantlab_context_market_decisions_pick_evidence_v2_check
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
                            policy_version LIKE 'CARDLAB_1XBET_POISSON_POLICY_%'
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
