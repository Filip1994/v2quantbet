-- GoalLab canonical pick sector and immutable settlement ledger.
-- One canonical GoalLab research pick per fixture/policy. This is separate from the
-- generic QuantLab shadow ledger and never touches production registered picks/bankroll.

CREATE TABLE quantlab_goal_picks (
    goal_pick_id TEXT PRIMARY KEY
        CHECK (goal_pick_id ~ '^quantlab-goal-pick-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    source_decision_id TEXT NOT NULL
        REFERENCES quantlab_goal_decisions(decision_id) ON DELETE RESTRICT,
    feature_snapshot_id TEXT NOT NULL
        REFERENCES quantlab_goal_feature_snapshots(feature_snapshot_id) ON DELETE RESTRICT,
    pick_policy_version TEXT NOT NULL
        CHECK (pick_policy_version = 'GOALLAB_DC_PLUS_PICK_POLICY_V1'),
    model_name TEXT NOT NULL CHECK (length(trim(model_name)) > 0),
    model_version TEXT NOT NULL
        CHECK (model_version ~ '^DC_PLUS_PRO_STRUCTURAL_V1:[0-9a-f]{64}$'),
    bookmaker_id BIGINT NOT NULL CHECK (bookmaker_id IN (8, 11)),
    bookmaker_name TEXT NOT NULL CHECK (length(trim(bookmaker_name)) > 0),
    provider_bet_id BIGINT NOT NULL CHECK (provider_bet_id > 0),
    provider_bet_name TEXT NOT NULL CHECK (length(trim(provider_bet_name)) > 0),
    market_key TEXT NOT NULL CHECK (market_key IN ('OU_25', 'BTTS')),
    selection TEXT NOT NULL CHECK (
        (market_key = 'OU_25' AND selection IN ('OVER', 'UNDER'))
        OR (market_key = 'BTTS' AND selection IN ('YES', 'NO'))
    ),
    line NUMERIC(10,3),
    selected_observation_id TEXT NOT NULL
        REFERENCES quantlab_market_observations(market_observation_id) ON DELETE RESTRICT,
    companion_observation_id TEXT NOT NULL
        REFERENCES quantlab_market_observations(market_observation_id) ON DELETE RESTRICT,
    quote_observed_at TIMESTAMPTZ NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    odds NUMERIC(12,5) NOT NULL CHECK (odds > 1),
    companion_odds NUMERIC(12,5) NOT NULL CHECK (companion_odds > 1),
    market_probability NUMERIC(12,9) NOT NULL
        CHECK (market_probability > 0 AND market_probability < 1),
    model_probability NUMERIC(12,9) NOT NULL
        CHECK (model_probability > 0 AND model_probability < 1),
    edge NUMERIC(12,9) NOT NULL,
    expected_value NUMERIC(12,9) NOT NULL,
    expected_home_goals NUMERIC(14,9) NOT NULL CHECK (expected_home_goals > 0),
    expected_away_goals NUMERIC(14,9) NOT NULL CHECK (expected_away_goals > 0),
    rho NUMERIC(14,9) NOT NULL,
    stake_minor BIGINT NOT NULL CHECK (stake_minor > 0),
    qualifying_candidate_count INTEGER NOT NULL CHECK (qualifying_candidate_count > 0),
    selection_rank_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (quote_observed_at <= decision_at),
    CHECK (decision_at < kickoff_at),
    UNIQUE (fixture_id, pick_policy_version),
    UNIQUE (goal_pick_id, fixture_id)
);

CREATE INDEX idx_quantlab_goal_picks_decision
    ON quantlab_goal_picks (decision_at DESC, goal_pick_id DESC);
CREATE INDEX idx_quantlab_goal_picks_model
    ON quantlab_goal_picks (model_version, decision_at DESC);
CREATE INDEX idx_quantlab_goal_picks_market
    ON quantlab_goal_picks (market_key, selection, decision_at DESC);

CREATE TRIGGER quantlab_goal_picks_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_picks
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_goal_pick_settlements (
    goal_pick_settlement_id TEXT PRIMARY KEY
        CHECK (goal_pick_settlement_id ~ '^quantlab-goal-settlement-v1:[0-9a-f]{64}$'),
    goal_pick_id TEXT NOT NULL,
    fixture_id TEXT NOT NULL,
    result_observation_id TEXT NOT NULL,
    result_classification TEXT NOT NULL
        CHECK (result_classification IN ('PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE')),
    regulation_home_goals INTEGER CHECK (regulation_home_goals IS NULL OR regulation_home_goals >= 0),
    regulation_away_goals INTEGER CHECK (regulation_away_goals IS NULL OR regulation_away_goals >= 0),
    outcome TEXT NOT NULL CHECK (outcome IN ('WIN', 'LOSS', 'VOID')),
    pnl_minor BIGINT NOT NULL,
    settled_at TIMESTAMPTZ NOT NULL,
    settlement_rule_version TEXT NOT NULL
        CHECK (settlement_rule_version = 'GOALLAB_SETTLEMENT_V1'),
    result_detail JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (goal_pick_id),
    FOREIGN KEY (goal_pick_id, fixture_id)
        REFERENCES quantlab_goal_picks(goal_pick_id, fixture_id) ON DELETE RESTRICT,
    FOREIGN KEY (result_observation_id, fixture_id)
        REFERENCES fixture_result_observations(result_observation_id, fixture_id)
        ON DELETE RESTRICT,
    CHECK (
        (result_classification = 'PLAYED_SETTLEABLE'
            AND regulation_home_goals IS NOT NULL
            AND regulation_away_goals IS NOT NULL
            AND outcome IN ('WIN', 'LOSS'))
        OR
        (result_classification = 'NON_PLAYED_VOIDABLE'
            AND regulation_home_goals IS NULL
            AND regulation_away_goals IS NULL
            AND outcome = 'VOID'
            AND pnl_minor = 0)
    )
);

CREATE INDEX idx_quantlab_goal_settlements_time
    ON quantlab_goal_pick_settlements (settled_at DESC);
CREATE INDEX idx_quantlab_goal_settlements_outcome
    ON quantlab_goal_pick_settlements (outcome, settled_at DESC);

CREATE TRIGGER quantlab_goal_pick_settlements_immutable
BEFORE UPDATE OR DELETE ON quantlab_goal_pick_settlements
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();
