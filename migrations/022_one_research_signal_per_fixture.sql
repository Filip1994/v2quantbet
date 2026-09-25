-- QuantBet research signals: enforce exactly one durable shadow pick per fixture.
--
-- Production already rejects duplicate fixtures. The research layer must mirror
-- that invariant so historical backfill and repeated opportunity cycles cannot
-- create multiple counterfactual picks for the same match.

ALTER TABLE research_signals
    ADD COLUMN fixture_id TEXT;

UPDATE research_signals rs
SET fixture_id = e.fixture_id
FROM value_evaluations e
WHERE e.evaluation_id = rs.evaluation_id;

ALTER TABLE research_signals
    ALTER COLUMN fixture_id SET NOT NULL;

ALTER TABLE research_signals
    ADD CONSTRAINT research_signals_fixture_fkey
    FOREIGN KEY (fixture_id) REFERENCES fixtures(fixture_id) ON DELETE RESTRICT;

-- Choose the counterfactual pick that would have been attempted first.
-- The worker orders candidates by EV, edge and odds before risk evaluation, so
-- the earliest blocked event is canonical; exact timestamp ties use the same
-- value-oriented deterministic ordering.
WITH ranked AS (
    SELECT
        rs.research_signal_id,
        rs.fixture_id,
        ROW_NUMBER() OVER (
            PARTITION BY rs.fixture_id
            ORDER BY
                rs.first_blocked_at ASC,
                e.expected_value DESC NULLS LAST,
                e.edge DESC NULLS LAST,
                e.selected_odd DESC NULLS LAST,
                rs.evaluation_id ASC
        ) AS fixture_rank,
        MAX(rs.last_blocked_at) OVER (
            PARTITION BY rs.fixture_id
        ) AS fixture_last_blocked_at,
        MAX(rs.blocked_count) OVER (
            PARTITION BY rs.fixture_id
        ) AS fixture_blocked_count
    FROM research_signals rs
    JOIN value_evaluations e ON e.evaluation_id = rs.evaluation_id
),
latest AS (
    SELECT DISTINCT ON (rs.fixture_id)
        rs.fixture_id,
        rs.last_open_exposure_minor,
        rs.exposure_cap_minor
    FROM research_signals rs
    ORDER BY rs.fixture_id, rs.last_blocked_at DESC, rs.evaluation_id ASC
),
rollup AS (
    SELECT
        ranked.research_signal_id,
        ranked.fixture_id,
        ranked.fixture_last_blocked_at,
        ranked.fixture_blocked_count,
        latest.last_open_exposure_minor,
        latest.exposure_cap_minor
    FROM ranked
    JOIN latest USING (fixture_id)
    WHERE ranked.fixture_rank = 1
)
UPDATE research_signals rs
SET
    last_blocked_at = rollup.fixture_last_blocked_at,
    blocked_count = GREATEST(rs.blocked_count, rollup.fixture_blocked_count),
    last_open_exposure_minor = rollup.last_open_exposure_minor,
    exposure_cap_minor = rollup.exposure_cap_minor
FROM rollup
WHERE rs.research_signal_id = rollup.research_signal_id;

WITH ranked AS (
    SELECT
        rs.research_signal_id,
        ROW_NUMBER() OVER (
            PARTITION BY rs.fixture_id
            ORDER BY
                rs.first_blocked_at ASC,
                e.expected_value DESC NULLS LAST,
                e.edge DESC NULLS LAST,
                e.selected_odd DESC NULLS LAST,
                rs.evaluation_id ASC
        ) AS fixture_rank
    FROM research_signals rs
    JOIN value_evaluations e ON e.evaluation_id = rs.evaluation_id
)
DELETE FROM research_signals rs
USING ranked
WHERE rs.research_signal_id = ranked.research_signal_id
  AND ranked.fixture_rank > 1;

ALTER TABLE research_signals
    ADD CONSTRAINT research_signals_fixture_key UNIQUE (fixture_id);
