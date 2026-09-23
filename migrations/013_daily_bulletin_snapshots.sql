-- Reproducible once-per-local-day projections over actionable registered picks.

CREATE TABLE daily_bulletins (
    bulletin_id TEXT PRIMARY KEY CHECK (bulletin_id ~ '^daily-bulletin-v1:[0-9a-f]{64}$'),
    bulletin_version TEXT NOT NULL CHECK (bulletin_version = 'DAILY_BULLETIN_V1'),
    local_date DATE NOT NULL,
    timezone TEXT NOT NULL CHECK (length(trim(timezone)) > 0),
    generated_at TIMESTAMPTZ NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    horizon_seconds INTEGER NOT NULL CHECK (horizon_seconds > 0),
    UNIQUE (local_date, timezone, bulletin_version)
);

CREATE TABLE daily_bulletin_memberships (
    bulletin_id TEXT NOT NULL REFERENCES daily_bulletins(bulletin_id) ON DELETE RESTRICT,
    pick_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    fixture_kickoff_at TIMESTAMPTZ NOT NULL,
    actionable_status TEXT NOT NULL CHECK (actionable_status = 'ACTIONABLE'),
    PRIMARY KEY (bulletin_id, pick_id),
    UNIQUE (bulletin_id, ordinal)
);

CREATE INDEX idx_daily_bulletins_generated
    ON daily_bulletins (generated_at, bulletin_id);
CREATE INDEX idx_daily_bulletin_memberships_pick
    ON daily_bulletin_memberships (pick_id, bulletin_id);
