-- QuantBet — immutable Dixon-Coles model artifacts and active pointers

CREATE TABLE IF NOT EXISTS dixon_coles_model_versions (
    model_version_id TEXT PRIMARY KEY
        CHECK (model_version_id ~ '^dcm-json-v1:[0-9a-f]{64}$'),
    provider TEXT NOT NULL CHECK (provider = 'api-football'),
    team_id_namespace TEXT NOT NULL CHECK (team_id_namespace = 'api-football'),
    league_id BIGINT NOT NULL CHECK (league_id > 0),
    season INTEGER NOT NULL CHECK (season > 0),
    training_start_at TIMESTAMPTZ NOT NULL,
    training_end_at TIMESTAMPTZ NOT NULL,
    reference_time TIMESTAMPTZ NOT NULL,
    xi DOUBLE PRECISION NOT NULL
        CHECK (xi >= 0.0 AND xi < 'Infinity'::double precision),
    ridge DOUBLE PRECISION NOT NULL
        CHECK (ridge >= 0.0 AND ridge < 'Infinity'::double precision),
    min_matches INTEGER NOT NULL CHECK (min_matches > 0),
    accepted_match_count INTEGER NOT NULL CHECK (accepted_match_count > 0),
    fitted_match_count INTEGER NOT NULL CHECK (fitted_match_count > 0),
    earliest_match_at TIMESTAMPTZ NOT NULL,
    latest_match_at TIMESTAMPTZ NOT NULL,
    dataset_sha256 TEXT NOT NULL CHECK (dataset_sha256 ~ '^[0-9a-f]{64}$'),
    training_input_fingerprint TEXT NOT NULL
        CHECK (training_input_fingerprint ~ '^[0-9a-f]{64}$'),
    trained_at TIMESTAMPTZ NOT NULL,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    artifact_schema_version INTEGER NOT NULL CHECK (artifact_schema_version = 1),
    training_dataset_schema_version INTEGER NOT NULL
        CHECK (training_dataset_schema_version = 1),
    model_implementation_version TEXT NOT NULL
        CHECK (length(trim(model_implementation_version)) > 0),
    trainer_code_version TEXT NOT NULL CHECK (length(trim(trainer_code_version)) > 0),
    python_version TEXT NOT NULL CHECK (length(trim(python_version)) > 0),
    numpy_version TEXT NOT NULL CHECK (length(trim(numpy_version)) > 0),
    scipy_version TEXT NOT NULL CHECK (length(trim(scipy_version)) > 0),
    artifact_sha256 TEXT NOT NULL UNIQUE CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    artifact_bytes BYTEA NOT NULL,
    CHECK (training_start_at < training_end_at),
    CHECK (reference_time >= training_end_at),
    CHECK (accepted_match_count = fitted_match_count),
    CHECK (accepted_match_count >= min_matches),
    CHECK (training_start_at <= earliest_match_at),
    CHECK (earliest_match_at <= latest_match_at),
    CHECK (latest_match_at < training_end_at),
    CHECK (model_version_id = 'dcm-json-v1:' || artifact_sha256),
    UNIQUE (provider, team_id_namespace, league_id, season, model_version_id)
);

CREATE INDEX IF NOT EXISTS idx_dixon_coles_versions_scope
    ON dixon_coles_model_versions
    (provider, team_id_namespace, league_id, season, trained_at, model_version_id);

CREATE INDEX IF NOT EXISTS idx_dixon_coles_versions_training_input
    ON dixon_coles_model_versions (training_input_fingerprint);

CREATE TABLE IF NOT EXISTS dixon_coles_active_models (
    provider TEXT NOT NULL,
    team_id_namespace TEXT NOT NULL,
    league_id BIGINT NOT NULL,
    season INTEGER NOT NULL,
    model_version_id TEXT NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL,
    generation BIGINT NOT NULL CHECK (generation > 0),
    PRIMARY KEY (provider, team_id_namespace, league_id, season),
    FOREIGN KEY (provider, team_id_namespace, league_id, season, model_version_id)
        REFERENCES dixon_coles_model_versions
        (provider, team_id_namespace, league_id, season, model_version_id)
        ON DELETE RESTRICT
);
