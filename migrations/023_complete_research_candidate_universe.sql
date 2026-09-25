-- QuantBet research universe: every canonical candidate that reaches the final
-- production-selection boundary, regardless of whether portfolio exposure allows
-- it to become a real-money pick.
--
-- Existing research rows are exposure-blocked candidates. Production picks are
-- added to the same fixture-unique universe. The analytical evaluation remains
-- the preliminary canonical candidate for comparability; production registration
-- remains normalized in registered_picks/pick_decisions.

ALTER TABLE research_signals
    ALTER COLUMN block_reason DROP NOT NULL,
    ALTER COLUMN first_blocked_at DROP NOT NULL,
    ALTER COLUMN last_blocked_at DROP NOT NULL,
    ALTER COLUMN blocked_count DROP NOT NULL,
    ALTER COLUMN first_open_exposure_minor DROP NOT NULL,
    ALTER COLUMN last_open_exposure_minor DROP NOT NULL,
    ALTER COLUMN exposure_cap_minor DROP NOT NULL;

ALTER TABLE research_signals
    ADD COLUMN qualified_at TIMESTAMPTZ,
    ADD COLUMN production_pick_id TEXT;

UPDATE research_signals
SET qualified_at = first_blocked_at
WHERE qualified_at IS NULL;

ALTER TABLE research_signals
    ALTER COLUMN qualified_at SET NOT NULL,
    ALTER COLUMN qualified_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE research_signals
    ADD CONSTRAINT research_signals_production_pick_key UNIQUE (production_pick_id);

CREATE INDEX idx_research_signals_qualified
    ON research_signals (qualified_at DESC, evaluation_id);

-- Recover every existing production pick into the unified research universe.
-- For picks with mandatory final-quote verification, use the original canonical
-- preliminary evaluation so production and exposure-blocked cohorts are measured
-- at the same research decision stage.
WITH production_candidates AS (
    SELECT DISTINCT ON (rp.fixture_id)
        rp.fixture_id,
        rp.pick_id,
        rp.registered_at,
        COALESCE(fqv.preliminary_evaluation_id, rp.evaluation_id) AS research_evaluation_id
    FROM registered_picks rp
    JOIN pick_decisions pd ON pd.decision_id = rp.decision_id
    LEFT JOIN final_quote_verifications fqv
        ON fqv.verification_id = pd.final_quote_verification_id
    ORDER BY rp.fixture_id, rp.registered_at ASC, rp.pick_id ASC
)
INSERT INTO research_signals (
    research_signal_id,
    evaluation_id,
    fixture_id,
    stage,
    block_reason,
    first_blocked_at,
    last_blocked_at,
    blocked_count,
    first_open_exposure_minor,
    last_open_exposure_minor,
    exposure_cap_minor,
    qualified_at,
    production_pick_id
)
SELECT
    'research-signal-v1:' || split_part(pc.research_evaluation_id, ':', 2),
    pc.research_evaluation_id,
    pc.fixture_id,
    'PRELIMINARY',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    pc.registered_at,
    pc.pick_id
FROM production_candidates pc
JOIN value_evaluations e ON e.evaluation_id = pc.research_evaluation_id
ON CONFLICT (fixture_id) DO UPDATE SET
    research_signal_id = EXCLUDED.research_signal_id,
    evaluation_id = EXCLUDED.evaluation_id,
    production_pick_id = EXCLUDED.production_pick_id,
    qualified_at = EXCLUDED.qualified_at,
    block_reason = NULL,
    first_blocked_at = NULL,
    last_blocked_at = NULL,
    blocked_count = NULL,
    first_open_exposure_minor = NULL,
    last_open_exposure_minor = NULL,
    exposure_cap_minor = NULL;
