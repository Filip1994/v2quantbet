-- QuantBet: API-Football live market-close proxy capture and proxy CLV

CREATE TABLE pick_live_close_observations (
    observation_id TEXT PRIMARY KEY
        CHECK (observation_id ~ '^pick-live-close-observation-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL,
    fixture_id TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('OU_25', 'BTTS')),
    selection TEXT NOT NULL CHECK (selection IN ('OVER', 'UNDER', 'YES', 'NO')),
    source TEXT NOT NULL CHECK (source = 'api-football-live'),
    live_bet_id INTEGER NOT NULL CHECK (live_bet_id > 0),
    live_bet_name TEXT NOT NULL CHECK (length(trim(live_bet_name)) > 0),
    odd NUMERIC NOT NULL CHECK (odd > 1),
    provider_observed_at TIMESTAMPTZ NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (market = 'OU_25' AND selection IN ('OVER', 'UNDER'))
        OR (market = 'BTTS' AND selection IN ('YES', 'NO'))
    ),
    FOREIGN KEY (pick_id, fixture_id)
        REFERENCES registered_picks(pick_id, fixture_id) ON DELETE RESTRICT,
    UNIQUE (observation_id, pick_id),
    UNIQUE (pick_id, provider_observed_at, live_bet_id, odd)
);

CREATE INDEX idx_pick_live_close_observations_latest
    ON pick_live_close_observations
    (pick_id, provider_observed_at DESC, captured_at DESC, observation_id DESC);

CREATE TABLE pick_live_close_finalizations (
    finalization_id TEXT PRIMARY KEY
        CHECK (finalization_id ~ '^pick-live-close-finalization-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL UNIQUE REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    cutoff_at TIMESTAMPTZ NOT NULL,
    finalized_at TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('CAPTURED', 'NO_VALID_QUOTE')),
    observation_id TEXT UNIQUE,
    entry_snapshot_id TEXT NOT NULL REFERENCES quote_snapshots(snapshot_id) ON DELETE RESTRICT,
    proxy_closing_odd_decimal NUMERIC CHECK (proxy_closing_odd_decimal > 1),
    proxy_clv_ppm BIGINT,
    source TEXT NOT NULL CHECK (source = 'api-football-live'),
    method_version TEXT NOT NULL
        CHECK (method_version = 'CLV_MARKET_PROXY_ODDS_RATIO_PPM_V1'),
    max_age_seconds INTEGER NOT NULL CHECK (max_age_seconds > 0),
    CHECK (finalized_at >= cutoff_at),
    FOREIGN KEY (observation_id, pick_id)
        REFERENCES pick_live_close_observations(observation_id, pick_id) ON DELETE RESTRICT,
    CHECK (
        (outcome = 'CAPTURED' AND observation_id IS NOT NULL
            AND proxy_closing_odd_decimal IS NOT NULL AND proxy_clv_ppm IS NOT NULL)
        OR
        (outcome = 'NO_VALID_QUOTE' AND observation_id IS NULL
            AND proxy_closing_odd_decimal IS NULL AND proxy_clv_ppm IS NULL)
    )
);

CREATE FUNCTION reject_live_close_proxy_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'live closing proxy facts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pick_live_close_observations_append_only
    BEFORE UPDATE OR DELETE ON pick_live_close_observations
    FOR EACH ROW EXECUTE FUNCTION reject_live_close_proxy_mutation();

CREATE TRIGGER pick_live_close_finalizations_append_only
    BEFORE UPDATE OR DELETE ON pick_live_close_finalizations
    FOR EACH ROW EXECUTE FUNCTION reject_live_close_proxy_mutation();
