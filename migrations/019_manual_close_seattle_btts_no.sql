-- QuantBet: operator-confirmed Seattle Sounders vs Real Salt Lake BTTS NO closing override.
-- Uses the latest same-book quote observed and captured before kickoff.

WITH latest_fixture AS (
    SELECT DISTINCT ON (fo.fixture_id)
        fo.fixture_id,
        fo.home_team,
        fo.away_team,
        fo.kickoff_at
    FROM fixture_observations fo
    ORDER BY fo.fixture_id, fo.observed_at DESC, fo.fixture_observation_id DESC
), target AS (
    SELECT
        r.pick_id,
        e.selected_series_id,
        e.source,
        latest.kickoff_at
    FROM registered_picks r
    JOIN value_evaluations e ON e.evaluation_id = r.evaluation_id
    JOIN latest_fixture latest ON latest.fixture_id = r.fixture_id
    WHERE r.registered_at >= TIMESTAMPTZ '2026-09-23 00:00:00+00'
      AND r.registered_at < TIMESTAMPTZ '2026-09-25 00:00:00+00'
      AND r.market = 'BTTS'
      AND r.selection = 'NO'
      AND (
        (
            latest.home_team ILIKE '%Seattle%'
            AND latest.away_team ILIKE '%Real Salt Lake%'
        ) OR (
            latest.away_team ILIKE '%Seattle%'
            AND latest.home_team ILIKE '%Real Salt Lake%'
        )
      )
      AND NOT EXISTS (
          SELECT 1
          FROM pick_closing_finalizations closing
          WHERE closing.pick_id = r.pick_id
            AND closing.outcome = 'CAPTURED'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM pick_manual_closing_overrides existing
          WHERE existing.pick_id = r.pick_id
      )
    ORDER BY r.registered_at DESC, r.pick_id DESC
    LIMIT 1
), last_observed AS (
    SELECT
        target.pick_id,
        quote.snapshot_id
    FROM target
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
    'manual-close-v1:f8a97d90528ea005ce6bb80525ab4665a5e34466fb17d2dac8350a78b655df2c',
    last_observed.pick_id,
    last_observed.snapshot_id,
    'operator-manual-last-observed',
    'Operator confirmed Seattle Sounders vs Real Salt Lake BTTS NO closing equals last observed.'
FROM last_observed
ON CONFLICT DO NOTHING;
