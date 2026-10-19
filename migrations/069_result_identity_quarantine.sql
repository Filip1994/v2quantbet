-- A conflicting provider identity needs explicit review before result polling resumes.
ALTER TABLE fixture_result_acquisition_states
    DROP CONSTRAINT fixture_result_acquisition_states_phase_check;
ALTER TABLE fixture_result_acquisition_states
    ADD CONSTRAINT fixture_result_acquisition_states_phase_check CHECK (phase IN (
        'WAITING', 'POLLING', 'STABILIZING', 'POST_SETTLEMENT_RECHECK',
        'COMPLETE', 'QUARANTINED'
    ));
ALTER TABLE fixture_result_acquisition_states
    ADD COLUMN quarantine_reason JSONB,
    ADD COLUMN quarantined_at TIMESTAMPTZ,
    ADD CONSTRAINT fixture_result_acquisition_states_quarantine_check CHECK (
        (phase = 'QUARANTINED' AND quarantine_reason IS NOT NULL AND quarantined_at IS NOT NULL)
        OR (phase <> 'QUARANTINED' AND quarantine_reason IS NULL AND quarantined_at IS NULL)
    );
