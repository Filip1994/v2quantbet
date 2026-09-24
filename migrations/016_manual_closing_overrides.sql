-- QuantBet: auditable manual closing overrides for explicitly operator-confirmed historical picks.

CREATE TABLE pick_manual_closing_overrides (
    override_id TEXT PRIMARY KEY
        CHECK (override_id ~ '^manual-close-v1:[0-9a-f]{64}$'),
    pick_id TEXT NOT NULL UNIQUE REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    snapshot_id TEXT NOT NULL REFERENCES quote_snapshots(snapshot_id) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (source = 'operator-manual-last-observed'),
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    entered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE FUNCTION reject_manual_closing_override_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'manual closing overrides are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pick_manual_closing_overrides_append_only
    BEFORE UPDATE OR DELETE ON pick_manual_closing_overrides
    FOR EACH ROW EXECUTE FUNCTION reject_manual_closing_override_mutation();

WITH latest_fixture AS (
    SELECT DISTINCT ON (fo.fixture_id)
        fo.fixture_id,
        fo.home_team,
        fo.away_team,
        fo.kickoff_at
    FROM fixture_observations fo
    ORDER BY fo.fixture_id, fo.observed_at DESC, fo.fixture_observation_id DESC
), candidates AS (
    SELECT
        CASE
            WHEN (
                latest.home_team ILIKE '%Seattle%'
                AND latest.away_team ILIKE '%Real Salt Lake%'
            ) OR (
                latest.away_team ILIKE '%Seattle%'
                AND latest.home_team ILIKE '%Real Salt Lake%'
            ) THEN 'seattle-rsl'
            WHEN latest.home_team ILIKE '%America%Cali%'
                OR latest.home_team ILIKE '%América%Cali%'
                OR latest.away_team ILIKE '%America%Cali%'
                OR latest.away_team ILIKE '%América%Cali%'
            THEN 'america-cali'
        END AS target_key,
        r.pick_id,
        r.registered_at,
        e.selected_series_id,
        e.source,
        latest.kickoff_at
    FROM registered_picks r
    JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id
    JOIN latest_fixture latest ON latest.fixture_id = r.fixture_id
    WHERE (
        (
            latest.home_team ILIKE '%Seattle%'
            AND latest.away_team ILIKE '%Real Salt Lake%'
        ) OR (
            latest.away_team ILIKE '%Seattle%'
            AND latest.home_team ILIKE '%Real Salt Lake%'
        ) OR latest.home_team ILIKE '%America%Cali%'
        OR latest.home_team ILIKE '%América%Cali%'
        OR latest.away_team ILIKE '%America%Cali%'
        OR latest.away_team ILIKE '%América%Cali%'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM pick_closing_finalizations closing
        WHERE closing.pick_id = r.pick_id
          AND closing.outcome = 'CAPTURED'
    )
), ranked AS (
    SELECT candidates.*,
        ROW_NUMBER() OVER (
            PARTITION BY target_key
            ORDER BY registered_at DESC, pick_id DESC
        ) AS rank
    FROM candidates
), targets AS (
    SELECT * FROM ranked WHERE rank = 1
), last_observed AS (
    SELECT
        target.target_key,
        target.pick_id,
        quote.snapshot_id
    FROM targets target
    JOIN LATERAL (
        SELECT q.snapshot_id
        FROM quote_snapshots q
        WHERE q.series_id = target.selected_series_id
          AND q.source = target.source
          AND q.observed_at < target.kickoff_at
          AND q.captured_at < target.kickoff_at
        ORDER BY q.observed_at DESC, q.captured_at DESC, q.snapshot_id DESC
        LIMIT 1
    ) quote ON TRUE
)
INSERT INTO pick_manual_closing_overrides (
    override_id,
    pick_id,
    snapshot_id,
    source,
    rationale
)
SELECT
    CASE last_observed.target_key
        WHEN 'seattle-rsl'
        THEN 'manual-close-v1:f8ec960e1979a3534ed81347048de6491e4cb223036d67b4614aa8ef7ceaec0d'
        WHEN 'america-cali'
        THEN 'manual-close-v1:a5c91bccafdbaefe7400c83b1a8c65f99a18334476bb6678c6b7f5366bb806c1'
    END,
    last_observed.pick_id,
    last_observed.snapshot_id,
    'operator-manual-last-observed',
    CASE last_observed.target_key
        WHEN 'seattle-rsl'
        THEN 'Operator confirmed Seattle Sounders vs Real Salt Lake closing equals last observed.'
        WHEN 'america-cali'
        THEN 'Operator confirmed America de Cali closing equals last observed.'
    END
FROM last_observed
ON CONFLICT DO NOTHING;
