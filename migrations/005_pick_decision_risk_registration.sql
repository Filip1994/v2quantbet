-- QuantBet — policy decisions, bankroll reservations, and immutable registered picks

ALTER TABLE value_evaluations
    ADD CONSTRAINT value_evaluations_selected_entry_key
    UNIQUE (
        evaluation_id, fixture_id, market, selected_selection, selected_snapshot_id
    );

CREATE TABLE pick_policy_configurations (
    config_fingerprint TEXT PRIMARY KEY
        CHECK (config_fingerprint ~ '^pick-policy-config-v1:[0-9a-f]{64}$'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    eligibility_policy_version TEXT NOT NULL
        CHECK (length(trim(eligibility_policy_version)) > 0),
    risk_policy_version TEXT NOT NULL CHECK (length(trim(risk_policy_version)) > 0),
    staking_policy_version TEXT NOT NULL CHECK (staking_policy_version = 'FIXED_STAKE_V1'),
    canonical_configuration TEXT NOT NULL
        CHECK (length(trim(canonical_configuration)) > 0),
    configuration JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bankroll_accounts (
    bankroll_account_id TEXT PRIMARY KEY CHECK (length(trim(bankroll_account_id)) > 0),
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE pick_decisions (
    decision_id TEXT PRIMARY KEY
        CHECK (decision_id ~ '^pick-decision-v1:[0-9a-f]{64}$'),
    registration_request_id TEXT NOT NULL UNIQUE
        CHECK (length(trim(registration_request_id)) > 0),
    evaluation_id TEXT NOT NULL REFERENCES value_evaluations(evaluation_id) ON DELETE RESTRICT,
    fixture_observation_id TEXT NOT NULL
        REFERENCES fixture_observations(fixture_observation_id) ON DELETE RESTRICT,
    config_fingerprint TEXT NOT NULL
        REFERENCES pick_policy_configurations(config_fingerprint) ON DELETE RESTRICT,
    decided_at TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('APPROVED', 'REJECTED')),
    rejection_stage TEXT CHECK (rejection_stage IN ('ELIGIBILITY', 'RISK')),
    reason_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    proposed_stake_minor BIGINT CHECK (proposed_stake_minor > 0),
    currency TEXT CHECK (currency ~ '^[A-Z]{3}$'),
    bankroll_account_id TEXT REFERENCES bankroll_accounts(bankroll_account_id) ON DELETE RESTRICT,
    bankroll_reference_entry_id TEXT,
    bankroll_balance_before_minor BIGINT,
    open_exposure_before_minor BIGINT CHECK (open_exposure_before_minor >= 0),
    CHECK (
        (outcome = 'APPROVED' AND rejection_stage IS NULL
            AND cardinality(reason_codes) = 0
            AND proposed_stake_minor IS NOT NULL AND currency IS NOT NULL
            AND bankroll_account_id IS NOT NULL AND bankroll_reference_entry_id IS NOT NULL
            AND bankroll_balance_before_minor IS NOT NULL
            AND open_exposure_before_minor IS NOT NULL)
        OR
        (outcome = 'REJECTED' AND rejection_stage = 'ELIGIBILITY'
            AND cardinality(reason_codes) > 0
            AND proposed_stake_minor IS NULL AND currency IS NULL
            AND bankroll_account_id IS NULL AND bankroll_reference_entry_id IS NULL
            AND bankroll_balance_before_minor IS NULL
            AND open_exposure_before_minor IS NULL)
        OR
        (outcome = 'REJECTED' AND rejection_stage = 'RISK'
            AND cardinality(reason_codes) > 0
            AND proposed_stake_minor IS NOT NULL AND currency IS NOT NULL
            AND bankroll_account_id IS NOT NULL AND bankroll_reference_entry_id IS NOT NULL
            AND bankroll_balance_before_minor IS NOT NULL
            AND open_exposure_before_minor IS NOT NULL)
    )
);

CREATE INDEX idx_pick_decisions_evaluation
    ON pick_decisions (evaluation_id, decided_at, decision_id);
CREATE INDEX idx_pick_decisions_outcome
    ON pick_decisions (outcome, decided_at, decision_id);

CREATE TABLE registered_picks (
    pick_id TEXT PRIMARY KEY CHECK (pick_id ~ '^registered-pick-v1:[0-9a-f]{64}$'),
    decision_id TEXT NOT NULL UNIQUE REFERENCES pick_decisions(decision_id) ON DELETE RESTRICT,
    evaluation_id TEXT NOT NULL UNIQUE,
    fixture_id TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('OU_25', 'BTTS')),
    selection TEXT NOT NULL,
    entry_snapshot_id TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    stake_minor BIGINT NOT NULL CHECK (stake_minor > 0),
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    bankroll_account_id TEXT NOT NULL
        REFERENCES bankroll_accounts(bankroll_account_id) ON DELETE RESTRICT,
    config_fingerprint TEXT NOT NULL
        REFERENCES pick_policy_configurations(config_fingerprint) ON DELETE RESTRICT,
    initial_state TEXT NOT NULL CHECK (initial_state = 'REGISTERED'),
    FOREIGN KEY (evaluation_id, fixture_id, market, selection, entry_snapshot_id)
        REFERENCES value_evaluations (
            evaluation_id, fixture_id, market, selected_selection, selected_snapshot_id
        ) ON DELETE RESTRICT,
    UNIQUE (fixture_id, market)
);

CREATE INDEX idx_registered_picks_registered
    ON registered_picks (registered_at, pick_id);
CREATE INDEX idx_registered_picks_bankroll
    ON registered_picks (bankroll_account_id, registered_at, pick_id);

CREATE TABLE bankroll_ledger_entries (
    ledger_entry_id TEXT PRIMARY KEY
        CHECK (ledger_entry_id ~ '^bankroll-entry-v1:[0-9a-f]{64}$'),
    bankroll_account_id TEXT NOT NULL
        REFERENCES bankroll_accounts(bankroll_account_id) ON DELETE RESTRICT,
    account_sequence BIGINT NOT NULL CHECK (account_sequence > 0),
    entry_type TEXT NOT NULL CHECK (entry_type IN ('INITIAL_BANKROLL', 'STAKE_RESERVED')),
    amount_minor BIGINT NOT NULL CHECK (amount_minor <> 0),
    balance_after_minor BIGINT NOT NULL CHECK (balance_after_minor >= 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    pick_id TEXT UNIQUE REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    UNIQUE (bankroll_account_id, account_sequence),
    CHECK (
        (entry_type = 'INITIAL_BANKROLL' AND amount_minor > 0 AND pick_id IS NULL)
        OR
        (entry_type = 'STAKE_RESERVED' AND amount_minor < 0 AND pick_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_bankroll_one_initial_entry
    ON bankroll_ledger_entries (bankroll_account_id)
    WHERE entry_type = 'INITIAL_BANKROLL';

CREATE INDEX idx_bankroll_ledger_order
    ON bankroll_ledger_entries (bankroll_account_id, account_sequence DESC);

ALTER TABLE pick_decisions
    ADD CONSTRAINT pick_decisions_bankroll_reference_fk
    FOREIGN KEY (bankroll_reference_entry_id)
    REFERENCES bankroll_ledger_entries(ledger_entry_id) ON DELETE RESTRICT;
