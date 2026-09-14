-- QuantBet — quote-history schema
-- PostgreSQL / Railway
-- This migration is intentionally append-only for quote observations.

CREATE TABLE IF NOT EXISTS quote_series (
    series_id TEXT PRIMARY KEY,
    fixture_id TEXT NOT NULL,
    bookmaker_id BIGINT NOT NULL CHECK (bookmaker_id > 0),
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (fixture_id, bookmaker_id, market, selection)
);

CREATE INDEX IF NOT EXISTS idx_quote_series_fixture
    ON quote_series (fixture_id, created_at, series_id);

CREATE TABLE IF NOT EXISTS quote_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    series_id TEXT NOT NULL REFERENCES quote_series(series_id),
    odd DOUBLE PRECISION NOT NULL CHECK (odd > 1.0 AND odd <> 'NaN'::double precision),
    observed_at TIMESTAMPTZ NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0),
    UNIQUE (series_id, observed_at, captured_at, source)
);

CREATE INDEX IF NOT EXISTS idx_quote_snapshots_series_order
    ON quote_snapshots (series_id, observed_at, captured_at, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_quote_snapshots_series_observed
    ON quote_snapshots (series_id, observed_at DESC, captured_at DESC);
