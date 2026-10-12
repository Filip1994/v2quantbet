-- Archive candidate selection and verified hot-row deletion check every
-- observation reference before removing a market observation. H2HLab was
-- added after the archive reference indexes and its two FK columns were not
-- indexed. Without these indexes each check scans the whole decisions table.
CREATE INDEX IF NOT EXISTS idx_quantlab_h2h_decisions_selected_observation
    ON quantlab_h2h_decisions (selected_observation_id)
    WHERE selected_observation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_quantlab_h2h_decisions_companion_observation
    ON quantlab_h2h_decisions (companion_observation_id)
    WHERE companion_observation_id IS NOT NULL;
