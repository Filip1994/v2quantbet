-- Research analytics: durable policy-version provenance for final-gate candidates.
-- Production candidates are backfilled from their immutable registered-pick configuration.
-- Legacy exposure-blocked rows remain explicitly unversioned rather than inferred.

ALTER TABLE research_signals
    ADD COLUMN policy_config_fingerprint TEXT,
    ADD COLUMN eligibility_policy_version TEXT,
    ADD COLUMN risk_policy_version TEXT,
    ADD COLUMN staking_policy_version TEXT,
    ADD COLUMN bookmaker_policy_version TEXT;

UPDATE research_signals rs
SET
    policy_config_fingerprint = r.config_fingerprint,
    eligibility_policy_version = config.eligibility_policy_version,
    risk_policy_version = config.risk_policy_version,
    staking_policy_version = config.staking_policy_version,
    bookmaker_policy_version = config.configuration ->> 'bookmaker_policy_version'
FROM registered_picks r
JOIN pick_policy_configurations config
    ON config.config_fingerprint = r.config_fingerprint
WHERE rs.production_pick_id = r.pick_id;

ALTER TABLE research_signals
    ADD CONSTRAINT research_signals_policy_snapshot_shape CHECK (
        (
            policy_config_fingerprint IS NULL
            AND eligibility_policy_version IS NULL
            AND risk_policy_version IS NULL
            AND staking_policy_version IS NULL
            AND bookmaker_policy_version IS NULL
        )
        OR
        (
            policy_config_fingerprint ~ '^pick-policy-config-v1:[0-9a-f]{64}$'
            AND eligibility_policy_version IS NOT NULL
            AND risk_policy_version IS NOT NULL
            AND staking_policy_version IS NOT NULL
            AND bookmaker_policy_version IS NOT NULL
        )
    );

CREATE INDEX idx_research_signals_policy_config
    ON research_signals (policy_config_fingerprint, qualified_at DESC)
    WHERE policy_config_fingerprint IS NOT NULL;
