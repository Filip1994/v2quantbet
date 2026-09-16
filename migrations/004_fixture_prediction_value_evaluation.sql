-- QuantBet — durable fixtures, production predictions, and value evaluations

CREATE TABLE fixtures (
    fixture_id TEXT PRIMARY KEY CHECK (length(trim(fixture_id)) > 0),
    provider TEXT NOT NULL CHECK (provider = 'api-football'),
    provider_fixture_id TEXT NOT NULL
        CHECK (provider_fixture_id ~ '^[1-9][0-9]*$'),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER NOT NULL CHECK (season > 0),
    provider_home_team_id BIGINT NOT NULL CHECK (provider_home_team_id > 0),
    provider_away_team_id BIGINT NOT NULL CHECK (provider_away_team_id > 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (fixture_id = provider || ':' || provider_fixture_id),
    CHECK (provider_home_team_id <> provider_away_team_id),
    UNIQUE (provider, provider_fixture_id),
    UNIQUE (
        fixture_id, provider, league_id, season,
        provider_home_team_id, provider_away_team_id
    )
);

CREATE TABLE fixture_observations (
    fixture_observation_id TEXT PRIMARY KEY
        CHECK (fixture_observation_id ~ '^fixture-observation-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    home_team TEXT NOT NULL CHECK (length(trim(home_team)) > 0),
    away_team TEXT NOT NULL CHECK (length(trim(away_team)) > 0),
    competition_name TEXT NOT NULL CHECK (length(trim(competition_name)) > 0),
    country TEXT NOT NULL CHECK (length(trim(country)) > 0),
    competition_type TEXT NOT NULL CHECK (length(trim(competition_type)) > 0),
    kickoff_at TIMESTAMPTZ NOT NULL,
    provider_status TEXT NOT NULL CHECK (length(trim(provider_status)) > 0),
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    observed_at TIMESTAMPTZ NOT NULL,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (fixture_id, observed_at, source),
    UNIQUE (fixture_observation_id, fixture_id)
);

CREATE INDEX idx_fixture_observations_latest
    ON fixture_observations (fixture_id, observed_at DESC, fixture_observation_id DESC);

CREATE TABLE fixture_predictions (
    prediction_id TEXT PRIMARY KEY
        CHECK (prediction_id ~ '^fixture-prediction-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL,
    fixture_observation_id TEXT NOT NULL,
    model_version_id TEXT NOT NULL,
    active_generation BIGINT NOT NULL CHECK (active_generation > 0),
    model_activated_at TIMESTAMPTZ NOT NULL,
    provider TEXT NOT NULL CHECK (provider = 'api-football'),
    team_id_namespace TEXT NOT NULL CHECK (team_id_namespace = 'api-football'),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER NOT NULL CHECK (season > 0),
    provider_home_team_id BIGINT NOT NULL CHECK (provider_home_team_id > 0),
    provider_away_team_id BIGINT NOT NULL CHECK (provider_away_team_id > 0),
    prediction_method_version TEXT NOT NULL
        CHECK (length(trim(prediction_method_version)) > 0),
    max_goals INTEGER NOT NULL CHECK (max_goals > 0),
    over_2_5_probability DOUBLE PRECISION NOT NULL,
    under_2_5_probability DOUBLE PRECISION NOT NULL,
    btts_yes_probability DOUBLE PRECISION NOT NULL,
    predicted_at TIMESTAMPTZ NOT NULL,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (provider_home_team_id <> provider_away_team_id),
    CHECK (
        over_2_5_probability <> 'NaN'::double precision
        AND over_2_5_probability >= 0.0 AND over_2_5_probability <= 1.0
    ),
    CHECK (
        under_2_5_probability <> 'NaN'::double precision
        AND under_2_5_probability >= 0.0 AND under_2_5_probability <= 1.0
    ),
    CHECK (
        btts_yes_probability <> 'NaN'::double precision
        AND btts_yes_probability >= 0.0 AND btts_yes_probability <= 1.0
    ),
    FOREIGN KEY (fixture_observation_id, fixture_id)
        REFERENCES fixture_observations(fixture_observation_id, fixture_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        fixture_id, provider, league_id, season,
        provider_home_team_id, provider_away_team_id
    ) REFERENCES fixtures (
        fixture_id, provider, league_id, season,
        provider_home_team_id, provider_away_team_id
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        provider, team_id_namespace, league_id, season, model_version_id
    ) REFERENCES dixon_coles_model_versions (
        provider, team_id_namespace, league_id, season, model_version_id
    ) ON DELETE RESTRICT,
    UNIQUE (
        fixture_observation_id, model_version_id, active_generation,
        prediction_method_version, max_goals
    ),
    UNIQUE (prediction_id, fixture_id, model_version_id)
);

ALTER TABLE quote_series
    ADD CONSTRAINT quote_series_context_key
    UNIQUE (series_id, fixture_id, bookmaker_id, market, selection);

ALTER TABLE quote_snapshots
    ADD CONSTRAINT quote_snapshots_context_key
    UNIQUE (snapshot_id, series_id, observed_at, captured_at, source, odd);

CREATE TABLE value_evaluations (
    evaluation_id TEXT PRIMARY KEY
        CHECK (evaluation_id ~ '^value-evaluation-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    prediction_id TEXT NOT NULL,
    model_version_id TEXT NOT NULL,
    selected_series_id TEXT NOT NULL,
    companion_series_id TEXT NOT NULL,
    selected_snapshot_id TEXT NOT NULL,
    companion_snapshot_id TEXT NOT NULL,
    bookmaker_id BIGINT NOT NULL CHECK (bookmaker_id > 0),
    bookmaker_key TEXT NOT NULL CHECK (length(trim(bookmaker_key)) > 0),
    market TEXT NOT NULL CHECK (market IN ('OU_25', 'BTTS')),
    selected_selection TEXT NOT NULL,
    companion_selection TEXT NOT NULL,
    quote_observed_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    selected_captured_at TIMESTAMPTZ NOT NULL,
    companion_captured_at TIMESTAMPTZ NOT NULL,
    selected_odd DOUBLE PRECISION NOT NULL,
    companion_odd DOUBLE PRECISION NOT NULL,
    selected_raw_implied_probability DOUBLE PRECISION NOT NULL,
    companion_raw_implied_probability DOUBLE PRECISION NOT NULL,
    overround DOUBLE PRECISION NOT NULL,
    devig_method_version TEXT NOT NULL
        CHECK (devig_method_version = 'PROPORTIONAL_TWO_WAY_V1'),
    selected_devig_probability DOUBLE PRECISION NOT NULL,
    model_probability DOUBLE PRECISION NOT NULL,
    edge DOUBLE PRECISION NOT NULL,
    expected_value DOUBLE PRECISION NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (selected_series_id <> companion_series_id),
    CHECK (selected_snapshot_id <> companion_snapshot_id),
    CHECK (selected_selection <> companion_selection),
    CHECK (
        (market = 'OU_25' AND selected_selection IN ('OVER', 'UNDER')
            AND companion_selection IN ('OVER', 'UNDER'))
        OR
        (market = 'BTTS' AND selected_selection IN ('YES', 'NO')
            AND companion_selection IN ('YES', 'NO'))
    ),
    CHECK (selected_odd > 1.0 AND selected_odd < 'Infinity'::double precision),
    CHECK (companion_odd > 1.0 AND companion_odd < 'Infinity'::double precision),
    CHECK (selected_raw_implied_probability >= 0.0
        AND selected_raw_implied_probability <= 1.0
        AND selected_raw_implied_probability <> 'NaN'::double precision),
    CHECK (companion_raw_implied_probability >= 0.0
        AND companion_raw_implied_probability <= 1.0
        AND companion_raw_implied_probability <> 'NaN'::double precision),
    CHECK (overround > 0.0 AND overround < 'Infinity'::double precision),
    CHECK (selected_devig_probability >= 0.0 AND selected_devig_probability <= 1.0
        AND selected_devig_probability <> 'NaN'::double precision),
    CHECK (model_probability >= 0.0 AND model_probability <= 1.0
        AND model_probability <> 'NaN'::double precision),
    CHECK (edge > '-Infinity'::double precision AND edge < 'Infinity'::double precision),
    CHECK (expected_value > '-Infinity'::double precision
        AND expected_value < 'Infinity'::double precision),
    FOREIGN KEY (prediction_id, fixture_id, model_version_id)
        REFERENCES fixture_predictions(prediction_id, fixture_id, model_version_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        selected_series_id, fixture_id, bookmaker_id, market, selected_selection
    ) REFERENCES quote_series(series_id, fixture_id, bookmaker_id, market, selection)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        companion_series_id, fixture_id, bookmaker_id, market, companion_selection
    ) REFERENCES quote_series(series_id, fixture_id, bookmaker_id, market, selection)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        selected_snapshot_id, selected_series_id, quote_observed_at,
        selected_captured_at, source, selected_odd
    ) REFERENCES quote_snapshots(
        snapshot_id, series_id, observed_at, captured_at, source, odd
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        companion_snapshot_id, companion_series_id, quote_observed_at,
        companion_captured_at, source, companion_odd
    ) REFERENCES quote_snapshots(
        snapshot_id, series_id, observed_at, captured_at, source, odd
    ) ON DELETE RESTRICT,
    UNIQUE (
        prediction_id, selected_snapshot_id, companion_snapshot_id,
        devig_method_version
    )
);

CREATE INDEX idx_value_evaluations_fixture
    ON value_evaluations (fixture_id, evaluated_at, evaluation_id);
