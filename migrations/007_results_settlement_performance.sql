-- QuantBet Task #12 — authoritative results, settlement, bankroll release, P&L and CLV

ALTER TABLE fixtures
    ADD CONSTRAINT fixtures_result_context_key
    UNIQUE (fixture_id, provider, provider_fixture_id);

CREATE TABLE fixture_result_observations (
    result_observation_id TEXT PRIMARY KEY
        CHECK (result_observation_id ~ '^fixture-result-observation-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (provider = 'api-football'),
    provider_fixture_id TEXT NOT NULL CHECK (provider_fixture_id ~ '^[1-9][0-9]*$'),
    provider_status TEXT NOT NULL CHECK (length(trim(provider_status)) > 0),
    provider_kickoff_at TIMESTAMPTZ NOT NULL,
    provider_home_team_id BIGINT NOT NULL CHECK (provider_home_team_id > 0),
    provider_away_team_id BIGINT NOT NULL CHECK (provider_away_team_id > 0),
    goals_home INTEGER CHECK (goals_home >= 0),
    goals_away INTEGER CHECK (goals_away >= 0),
    fulltime_home INTEGER CHECK (fulltime_home >= 0),
    fulltime_away INTEGER CHECK (fulltime_away >= 0),
    extratime_home INTEGER CHECK (extratime_home >= 0),
    extratime_away INTEGER CHECK (extratime_away >= 0),
    penalty_home INTEGER CHECK (penalty_home >= 0),
    penalty_away INTEGER CHECK (penalty_away >= 0),
    regulation_home_goals INTEGER CHECK (regulation_home_goals >= 0),
    regulation_away_goals INTEGER CHECK (regulation_away_goals >= 0),
    result_classification TEXT NOT NULL CHECK (result_classification IN (
        'NON_TERMINAL', 'PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE',
        'INVALID_TERMINAL', 'UNKNOWN_STATUS'
    )),
    settlement_fingerprint TEXT,
    normalizer_version TEXT NOT NULL
        CHECK (normalizer_version = 'API_FOOTBALL_SETTLEMENT_RESULT_V1'),
    provider_record_sha256 TEXT NOT NULL CHECK (provider_record_sha256 ~ '^[0-9a-f]{64}$'),
    provider_record JSONB NOT NULL,
    first_acquired_at TIMESTAMPTZ NOT NULL,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (provider_home_team_id <> provider_away_team_id),
    CHECK ((goals_home IS NULL) = (goals_away IS NULL)),
    CHECK ((fulltime_home IS NULL) = (fulltime_away IS NULL)),
    CHECK ((extratime_home IS NULL) = (extratime_away IS NULL)),
    CHECK ((penalty_home IS NULL) = (penalty_away IS NULL)),
    CHECK ((regulation_home_goals IS NULL) = (regulation_away_goals IS NULL)),
    CHECK (
        (result_classification IN ('PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE')
            AND settlement_fingerprint IS NOT NULL)
        OR
        (result_classification NOT IN ('PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE')
            AND settlement_fingerprint IS NULL)
    ),
    CHECK (
        result_classification <> 'PLAYED_SETTLEABLE'
        OR (regulation_home_goals IS NOT NULL AND regulation_away_goals IS NOT NULL)
    ),
    FOREIGN KEY (fixture_id, provider, provider_fixture_id)
        REFERENCES fixtures(fixture_id, provider, provider_fixture_id) ON DELETE RESTRICT,
    UNIQUE (fixture_id, provider_record_sha256, normalizer_version),
    UNIQUE (result_observation_id, fixture_id)
);

CREATE INDEX idx_fixture_result_observations_latest
    ON fixture_result_observations
    (fixture_id, first_acquired_at DESC, result_observation_id DESC);
CREATE INDEX idx_fixture_result_observations_fingerprint
    ON fixture_result_observations (fixture_id, settlement_fingerprint)
    WHERE settlement_fingerprint IS NOT NULL;

CREATE TABLE fixture_result_acquisition_states (
    fixture_id TEXT PRIMARY KEY REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    phase TEXT NOT NULL CHECK (phase IN (
        'WAITING', 'POLLING', 'STABILIZING', 'POST_SETTLEMENT_RECHECK', 'COMPLETE'
    )),
    current_observation_id TEXT,
    candidate_observation_id TEXT,
    candidate_settlement_fingerprint TEXT,
    candidate_first_seen_at TIMESTAMPTZ,
    candidate_confirmation_count INTEGER NOT NULL DEFAULT 0
        CHECK (candidate_confirmation_count >= 0),
    next_check_at TIMESTAMPTZ NOT NULL,
    lease_expires_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    correction_required BOOLEAN NOT NULL DEFAULT FALSE,
    contradicting_observation_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL CHECK (version > 0),
    FOREIGN KEY (current_observation_id, fixture_id)
        REFERENCES fixture_result_observations(result_observation_id, fixture_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (candidate_observation_id, fixture_id)
        REFERENCES fixture_result_observations(result_observation_id, fixture_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (contradicting_observation_id, fixture_id)
        REFERENCES fixture_result_observations(result_observation_id, fixture_id)
        ON DELETE RESTRICT,
    CHECK (
        (candidate_observation_id IS NULL AND candidate_settlement_fingerprint IS NULL
            AND candidate_first_seen_at IS NULL AND candidate_confirmation_count = 0)
        OR
        (candidate_observation_id IS NOT NULL AND candidate_settlement_fingerprint IS NOT NULL
            AND candidate_first_seen_at IS NOT NULL AND candidate_confirmation_count > 0)
    ),
    CHECK (
        (correction_required AND contradicting_observation_id IS NOT NULL)
        OR (NOT correction_required AND contradicting_observation_id IS NULL)
    )
);

CREATE INDEX idx_fixture_result_acquisition_due
    ON fixture_result_acquisition_states (next_check_at, fixture_id)
    WHERE phase <> 'COMPLETE';
CREATE INDEX idx_fixture_result_acquisition_lease
    ON fixture_result_acquisition_states (lease_expires_at, fixture_id)
    WHERE lease_expires_at IS NOT NULL;

ALTER TABLE bankroll_ledger_entries
    DROP CONSTRAINT IF EXISTS bankroll_ledger_entries_pick_id_key;
ALTER TABLE bankroll_ledger_entries
    DROP CONSTRAINT IF EXISTS bankroll_ledger_entries_entry_type_check;
ALTER TABLE bankroll_ledger_entries
    DROP CONSTRAINT IF EXISTS bankroll_ledger_entries_amount_minor_check;
ALTER TABLE bankroll_ledger_entries
    DROP CONSTRAINT IF EXISTS bankroll_ledger_entries_balance_after_minor_check;
ALTER TABLE bankroll_ledger_entries
    DROP CONSTRAINT IF EXISTS bankroll_ledger_entries_check;

ALTER TABLE bankroll_ledger_entries
    ADD CONSTRAINT bankroll_ledger_entries_entry_type_check CHECK (entry_type IN (
        'INITIAL_BANKROLL', 'STAKE_RESERVED', 'PAYOUT', 'LOSS', 'VOID_REFUND',
        'SETTLEMENT_ADJUSTMENT', 'SETTLEMENT_REVERSAL'
    ));
ALTER TABLE bankroll_ledger_entries
    ADD CONSTRAINT bankroll_ledger_entries_shape_check CHECK (
        (entry_type = 'INITIAL_BANKROLL' AND amount_minor > 0 AND pick_id IS NULL)
        OR
        (entry_type = 'STAKE_RESERVED' AND amount_minor < 0 AND pick_id IS NOT NULL)
        OR
        (entry_type = 'PAYOUT' AND amount_minor > 0 AND pick_id IS NOT NULL)
        OR
        (entry_type = 'LOSS' AND amount_minor = 0 AND pick_id IS NOT NULL)
        OR
        (entry_type = 'VOID_REFUND' AND amount_minor > 0 AND pick_id IS NOT NULL)
        OR
        (entry_type IN ('SETTLEMENT_ADJUSTMENT', 'SETTLEMENT_REVERSAL')
            AND pick_id IS NOT NULL)
    );

CREATE UNIQUE INDEX uq_bankroll_one_reservation_per_pick
    ON bankroll_ledger_entries (pick_id)
    WHERE entry_type = 'STAKE_RESERVED';

CREATE TABLE pick_settlement_events (
    settlement_event_id TEXT PRIMARY KEY
        CHECK (settlement_event_id ~ '^pick-settlement-event-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL,
    fixture_id TEXT NOT NULL,
    event_kind TEXT NOT NULL CHECK (event_kind IN ('NORMAL', 'CORRECTION', 'REVERSAL')),
    prior_event_id TEXT,
    result_observation_id TEXT NOT NULL,
    outcome TEXT CHECK (outcome IN ('WIN', 'LOSS', 'VOID')),
    settlement_rule_version TEXT NOT NULL
        CHECK (settlement_rule_version = 'SETTLEMENT_OU25_BTTS_REGULATION_V1'),
    rounding_version TEXT NOT NULL CHECK (rounding_version = 'MONEY_HALF_UP_V1'),
    entry_snapshot_id TEXT NOT NULL,
    entry_odd_decimal NUMERIC NOT NULL CHECK (entry_odd_decimal > 1),
    stake_minor BIGINT NOT NULL CHECK (stake_minor > 0),
    gross_return_minor BIGINT CHECK (gross_return_minor >= 0),
    realized_pnl_minor BIGINT,
    ledger_delta_minor BIGINT NOT NULL,
    bankroll_account_id TEXT NOT NULL
        REFERENCES bankroll_accounts(bankroll_account_id) ON DELETE RESTRICT,
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    ledger_entry_id TEXT NOT NULL UNIQUE
        REFERENCES bankroll_ledger_entries(ledger_entry_id) ON DELETE RESTRICT,
    candidate_first_seen_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    confirmation_count INTEGER NOT NULL CHECK (confirmation_count >= 2),
    request_id TEXT NOT NULL UNIQUE CHECK (length(trim(request_id)) > 0),
    reason TEXT,
    actor TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (pick_id, fixture_id)
        REFERENCES registered_picks(pick_id, fixture_id) ON DELETE RESTRICT,
    FOREIGN KEY (result_observation_id, fixture_id)
        REFERENCES fixture_result_observations(result_observation_id, fixture_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (prior_event_id, pick_id)
        REFERENCES pick_settlement_events(settlement_event_id, pick_id) ON DELETE RESTRICT,
    FOREIGN KEY (entry_snapshot_id)
        REFERENCES quote_snapshots(snapshot_id) ON DELETE RESTRICT,
    UNIQUE (settlement_event_id, pick_id),
    UNIQUE (prior_event_id),
    CHECK (confirmed_at >= candidate_first_seen_at),
    CHECK (
        (event_kind = 'NORMAL' AND prior_event_id IS NULL AND outcome IS NOT NULL
            AND gross_return_minor IS NOT NULL AND realized_pnl_minor IS NOT NULL
            AND reason IS NULL AND actor IS NULL)
        OR
        (event_kind = 'CORRECTION' AND prior_event_id IS NOT NULL AND outcome IS NOT NULL
            AND gross_return_minor IS NOT NULL AND realized_pnl_minor IS NOT NULL
            AND reason IS NOT NULL AND actor IS NOT NULL)
        OR
        (event_kind = 'REVERSAL' AND prior_event_id IS NOT NULL AND outcome IS NULL
            AND gross_return_minor IS NULL AND realized_pnl_minor IS NULL
            AND reason IS NOT NULL AND actor IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_pick_one_normal_settlement
    ON pick_settlement_events (pick_id) WHERE event_kind = 'NORMAL';
CREATE INDEX idx_pick_settlement_history
    ON pick_settlement_events (pick_id, occurred_at, settlement_event_id);
CREATE INDEX idx_pick_settlement_result
    ON pick_settlement_events (result_observation_id, pick_id);

CREATE TABLE pick_realized_clv (
    clv_fact_id TEXT PRIMARY KEY
        CHECK (clv_fact_id ~ '^pick-realized-clv-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL UNIQUE REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    settlement_event_id TEXT NOT NULL UNIQUE
        REFERENCES pick_settlement_events(settlement_event_id) ON DELETE RESTRICT,
    closing_finalization_id TEXT NOT NULL UNIQUE
        REFERENCES pick_closing_finalizations(finalization_id) ON DELETE RESTRICT,
    entry_snapshot_id TEXT NOT NULL,
    closing_snapshot_id TEXT NOT NULL,
    series_id TEXT NOT NULL REFERENCES quote_series(series_id) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    entry_odd_decimal NUMERIC NOT NULL CHECK (entry_odd_decimal > 1),
    closing_odd_decimal NUMERIC NOT NULL CHECK (closing_odd_decimal > 1),
    method_version TEXT NOT NULL CHECK (method_version = 'CLV_ODDS_RATIO_PPM_V1'),
    clv_ppm BIGINT NOT NULL,
    realized_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (entry_snapshot_id, series_id, source)
        REFERENCES quote_snapshots(snapshot_id, series_id, source) ON DELETE RESTRICT,
    FOREIGN KEY (closing_snapshot_id, series_id, source)
        REFERENCES quote_snapshots(snapshot_id, series_id, source) ON DELETE RESTRICT
);

CREATE INDEX idx_pick_realized_clv_value ON pick_realized_clv (clv_ppm, pick_id);

CREATE FUNCTION reject_task12_fact_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Task #12 result and financial facts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER fixture_result_observations_append_only
    BEFORE UPDATE OR DELETE ON fixture_result_observations
    FOR EACH ROW EXECUTE FUNCTION reject_task12_fact_mutation();
CREATE TRIGGER pick_settlement_events_append_only
    BEFORE UPDATE OR DELETE ON pick_settlement_events
    FOR EACH ROW EXECUTE FUNCTION reject_task12_fact_mutation();
CREATE TRIGGER pick_realized_clv_append_only
    BEFORE UPDATE OR DELETE ON pick_realized_clv
    FOR EACH ROW EXECUTE FUNCTION reject_task12_fact_mutation();
CREATE TRIGGER bankroll_ledger_entries_append_only
    BEFORE UPDATE OR DELETE ON bankroll_ledger_entries
    FOR EACH ROW EXECUTE FUNCTION reject_task12_fact_mutation();
