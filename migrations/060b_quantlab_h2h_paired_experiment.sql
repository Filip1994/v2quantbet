-- H2HLab paired experiment: freeze DC-only and DC+H2H policies on the same evidence.
-- Ordered after 060a H2HLab V1 while preserving 063 as the schema tip expected by legacy tests.

CREATE TABLE quantlab_h2h_experiments (
    experiment_id TEXT PRIMARY KEY
        CHECK (experiment_id ~ '^quantlab-h2h-experiment-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL
        REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    h2h_snapshot_id TEXT NOT NULL
        REFERENCES quantlab_h2h_snapshots(h2h_snapshot_id) ON DELETE RESTRICT,
    frozen_at TIMESTAMPTZ NOT NULL,
    experiment_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    h2h_sample_size INTEGER NOT NULL CHECK (h2h_sample_size BETWEEN 5 AND 10),
    dc_weight NUMERIC(12,9) NOT NULL CHECK (dc_weight >= 0 AND dc_weight <= 0.70),
    h2h_weight NUMERIC(12,9) NOT NULL CHECK (h2h_weight >= 0.30 AND h2h_weight <= 1),
    relation TEXT NOT NULL CHECK (
        relation IN (
            'SAME_BET',
            'SAME_SIDE_DIFFERENT_PRICE',
            'FLIP',
            'DIFFERENT_MARKET',
            'H2H_ONLY',
            'DC_ONLY',
            'BOTH_NO_BET'
        )
    ),
    dc_arm JSONB NOT NULL,
    h2h_arm JSONB NOT NULL,
    probability_trials JSONB NOT NULL,
    evidence_fingerprint TEXT NOT NULL CHECK (evidence_fingerprint ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (fixture_id, experiment_version),
    CHECK (abs((dc_weight + h2h_weight) - 1.0) < 0.000001)
);

CREATE INDEX idx_quantlab_h2h_experiments_frozen
    ON quantlab_h2h_experiments (frozen_at DESC, experiment_id DESC);

CREATE TRIGGER quantlab_h2h_experiments_immutable
BEFORE UPDATE OR DELETE ON quantlab_h2h_experiments
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_h2h_experiment_settlements (
    settlement_id TEXT PRIMARY KEY
        CHECK (settlement_id ~ '^quantlab-h2h-experiment-settlement-v1:[0-9a-f]{64}$'),
    experiment_id TEXT NOT NULL UNIQUE
        REFERENCES quantlab_h2h_experiments(experiment_id) ON DELETE RESTRICT,
    fixture_id TEXT NOT NULL
        REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    settled_at TIMESTAMPTZ NOT NULL,
    provider_status TEXT NOT NULL,
    home_goals INTEGER CHECK (home_goals IS NULL OR home_goals >= 0),
    away_goals INTEGER CHECK (away_goals IS NULL OR away_goals >= 0),
    dc_outcome TEXT NOT NULL CHECK (dc_outcome IN ('WIN','LOSS','VOID','NO_BET')),
    h2h_outcome TEXT NOT NULL CHECK (h2h_outcome IN ('WIN','LOSS','VOID','NO_BET')),
    dc_pnl_minor BIGINT NOT NULL,
    h2h_pnl_minor BIGINT NOT NULL,
    outcome_regime TEXT NOT NULL,
    dc_brier_mean NUMERIC(14,12),
    h2h_brier_mean NUMERIC(14,12),
    brier_uplift NUMERIC(14,12),
    probability_trials JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_h2h_experiment_settlements_fixture
    ON quantlab_h2h_experiment_settlements (fixture_id, settled_at DESC);

CREATE TRIGGER quantlab_h2h_experiment_settlements_immutable
BEFORE UPDATE OR DELETE ON quantlab_h2h_experiment_settlements
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
