-- CornerLab V2: pressure-statistics model, acquisition watermarks and model audit.
-- Production prediction/registration/bankroll state remains untouched.

ALTER TABLE quantlab_match_statistics_observations
    ADD COLUMN home_corner_kicks INTEGER CHECK (home_corner_kicks IS NULL OR home_corner_kicks >= 0),
    ADD COLUMN away_corner_kicks INTEGER CHECK (away_corner_kicks IS NULL OR away_corner_kicks >= 0),
    ADD COLUMN home_ball_possession NUMERIC(7,3)
        CHECK (home_ball_possession IS NULL OR (home_ball_possession >= 0 AND home_ball_possession <= 100)),
    ADD COLUMN away_ball_possession NUMERIC(7,3)
        CHECK (away_ball_possession IS NULL OR (away_ball_possession >= 0 AND away_ball_possession <= 100)),
    ADD COLUMN home_shots_on_goal INTEGER CHECK (home_shots_on_goal IS NULL OR home_shots_on_goal >= 0),
    ADD COLUMN away_shots_on_goal INTEGER CHECK (away_shots_on_goal IS NULL OR away_shots_on_goal >= 0),
    ADD COLUMN home_shots_off_goal INTEGER CHECK (home_shots_off_goal IS NULL OR home_shots_off_goal >= 0),
    ADD COLUMN away_shots_off_goal INTEGER CHECK (away_shots_off_goal IS NULL OR away_shots_off_goal >= 0),
    ADD COLUMN home_total_shots INTEGER CHECK (home_total_shots IS NULL OR home_total_shots >= 0),
    ADD COLUMN away_total_shots INTEGER CHECK (away_total_shots IS NULL OR away_total_shots >= 0),
    ADD COLUMN home_blocked_shots INTEGER CHECK (home_blocked_shots IS NULL OR home_blocked_shots >= 0),
    ADD COLUMN away_blocked_shots INTEGER CHECK (away_blocked_shots IS NULL OR away_blocked_shots >= 0),
    ADD COLUMN home_shots_insidebox INTEGER CHECK (home_shots_insidebox IS NULL OR home_shots_insidebox >= 0),
    ADD COLUMN away_shots_insidebox INTEGER CHECK (away_shots_insidebox IS NULL OR away_shots_insidebox >= 0),
    ADD COLUMN home_shots_outsidebox INTEGER CHECK (home_shots_outsidebox IS NULL OR home_shots_outsidebox >= 0),
    ADD COLUMN away_shots_outsidebox INTEGER CHECK (away_shots_outsidebox IS NULL OR away_shots_outsidebox >= 0),
    ADD COLUMN home_offsides INTEGER CHECK (home_offsides IS NULL OR home_offsides >= 0),
    ADD COLUMN away_offsides INTEGER CHECK (away_offsides IS NULL OR away_offsides >= 0),
    ADD COLUMN home_goalkeeper_saves INTEGER
        CHECK (home_goalkeeper_saves IS NULL OR home_goalkeeper_saves >= 0),
    ADD COLUMN away_goalkeeper_saves INTEGER
        CHECK (away_goalkeeper_saves IS NULL OR away_goalkeeper_saves >= 0),
    ADD COLUMN home_total_passes INTEGER CHECK (home_total_passes IS NULL OR home_total_passes >= 0),
    ADD COLUMN away_total_passes INTEGER CHECK (away_total_passes IS NULL OR away_total_passes >= 0),
    ADD COLUMN home_passes_accurate INTEGER
        CHECK (home_passes_accurate IS NULL OR home_passes_accurate >= 0),
    ADD COLUMN away_passes_accurate INTEGER
        CHECK (away_passes_accurate IS NULL OR away_passes_accurate >= 0),
    ADD COLUMN home_pass_accuracy NUMERIC(7,3)
        CHECK (home_pass_accuracy IS NULL OR (home_pass_accuracy >= 0 AND home_pass_accuracy <= 100)),
    ADD COLUMN away_pass_accuracy NUMERIC(7,3)
        CHECK (away_pass_accuracy IS NULL OR (away_pass_accuracy >= 0 AND away_pass_accuracy <= 100));

CREATE TABLE quantlab_statistics_captures (
    statistics_capture_id TEXT PRIMARY KEY
        CHECK (statistics_capture_id ~ '^quantlab-stats-capture-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE', 'UNAVAILABLE')),
    response_team_count INTEGER NOT NULL CHECK (response_team_count >= 0),
    reason TEXT,
    raw_payload JSONB NOT NULL
);

CREATE INDEX idx_quantlab_stats_capture_fixture
    ON quantlab_statistics_captures (fixture_id, captured_at DESC);

CREATE TRIGGER quantlab_statistics_captures_immutable
BEFORE UPDATE OR DELETE ON quantlab_statistics_captures
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

INSERT INTO quantlab_statistics_captures (
    statistics_capture_id,
    fixture_id,
    provider_fixture_id,
    captured_at,
    status,
    response_team_count,
    reason,
    raw_payload
)
SELECT
    'quantlab-stats-capture-v1:' || encode(
        sha256(
            convert_to(
                s.fixture_id || ':' || s.provider_fixture_id::TEXT || ':' ||
                s.available_at::TEXT || ':legacy-available',
                'UTF8'
            )
        ),
        'hex'
    ),
    s.fixture_id,
    s.provider_fixture_id,
    s.available_at,
    'AVAILABLE',
    2,
    'legacy-statistics-observation',
    s.raw_payload
FROM quantlab_match_statistics_observations s
ON CONFLICT DO NOTHING;

CREATE TABLE quantlab_corner_model_versions (
    model_version TEXT PRIMARY KEY
        CHECK (model_version ~ '^CORNER_PRESSURE_POISSON_V1:[0-9a-f]{64}$'),
    trained_at TIMESTAMPTZ NOT NULL,
    training_cutoff TIMESTAMPTZ NOT NULL,
    feature_version TEXT NOT NULL CHECK (feature_version = 'CORNER_PRESSURE_FEATURES_V1'),
    training_sample_size INTEGER NOT NULL CHECK (training_sample_size > 0),
    history_match_count INTEGER NOT NULL CHECK (history_match_count > 0),
    ridge_penalty NUMERIC(14,6) NOT NULL CHECK (ridge_penalty > 0),
    coefficients JSONB NOT NULL,
    feature_means JSONB NOT NULL,
    feature_scales JSONB NOT NULL,
    training_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER quantlab_corner_models_immutable
BEFORE UPDATE OR DELETE ON quantlab_corner_model_versions
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_corner_feature_snapshots (
    feature_snapshot_id TEXT PRIMARY KEY
        CHECK (feature_snapshot_id ~ '^quantlab-corner-features-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    decision_at TIMESTAMPTZ NOT NULL,
    model_version TEXT NOT NULL
        REFERENCES quantlab_corner_model_versions(model_version) ON DELETE RESTRICT,
    expected_total_corners NUMERIC(12,6) NOT NULL CHECK (expected_total_corners > 0),
    home_history_size INTEGER NOT NULL CHECK (home_history_size >= 0),
    away_history_size INTEGER NOT NULL CHECK (away_history_size >= 0),
    feature_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (fixture_id, decision_at, model_version)
);

CREATE INDEX idx_quantlab_corner_features_fixture
    ON quantlab_corner_feature_snapshots (fixture_id, decision_at DESC);

CREATE TRIGGER quantlab_corner_features_immutable
BEFORE UPDATE OR DELETE ON quantlab_corner_feature_snapshots
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

ALTER TABLE quantlab_context_market_decisions
    DROP CONSTRAINT IF EXISTS quantlab_context_market_decisions_check;

ALTER TABLE quantlab_context_market_decisions
    ADD CONSTRAINT quantlab_context_market_decisions_pick_evidence_check
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
                    reference_bookmaker_id IS NOT NULL
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
    );
