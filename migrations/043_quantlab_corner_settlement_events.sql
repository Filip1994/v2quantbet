-- CornerLab immutable settlement event ledger.
-- Existing settled shadow rows are preserved as LEGACY_BACKFILL events.
-- New CornerLab settlements are append-only and no longer mutate quantlab_shadow_bets.

CREATE TABLE quantlab_corner_settlement_events (
    corner_settlement_event_id TEXT PRIMARY KEY
        CHECK (corner_settlement_event_id ~ '^quantlab-corner-settlement-event-v1:[0-9a-f]{64}$'),
    shadow_bet_id TEXT NOT NULL
        REFERENCES quantlab_shadow_bets(shadow_bet_id) ON DELETE RESTRICT,
    fixture_id TEXT NOT NULL
        REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    event_kind TEXT NOT NULL
        CHECK (event_kind IN ('NORMAL', 'CORRECTION', 'REVERSAL', 'LEGACY_BACKFILL')),
    prior_event_id TEXT,
    result_observation_id TEXT
        REFERENCES fixture_result_observations(result_observation_id) ON DELETE RESTRICT,
    statistics_observation_id TEXT
        REFERENCES quantlab_match_statistics_observations(statistics_observation_id)
        ON DELETE RESTRICT,
    result_classification TEXT
        CHECK (
            result_classification IS NULL
            OR result_classification IN ('PLAYED_SETTLEABLE', 'NON_PLAYED_VOIDABLE')
        ),
    outcome TEXT CHECK (outcome IS NULL OR outcome IN ('WIN', 'LOSS', 'VOID')),
    pnl_minor BIGINT,
    occurred_at TIMESTAMPTZ NOT NULL,
    settlement_rule_version TEXT NOT NULL
        CHECK (settlement_rule_version = 'CORNERLAB_TOTAL_CORNERS_HALF_LINE_SETTLEMENT_V1'),
    result_detail JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (corner_settlement_event_id, shadow_bet_id),
    UNIQUE (prior_event_id),
    FOREIGN KEY (prior_event_id, shadow_bet_id)
        REFERENCES quantlab_corner_settlement_events(corner_settlement_event_id, shadow_bet_id)
        ON DELETE RESTRICT,
    CHECK (
        (event_kind = 'NORMAL'
            AND prior_event_id IS NULL
            AND result_observation_id IS NOT NULL
            AND result_classification IS NOT NULL
            AND outcome IS NOT NULL
            AND pnl_minor IS NOT NULL)
        OR
        (event_kind = 'LEGACY_BACKFILL'
            AND prior_event_id IS NULL
            AND result_classification IS NOT NULL
            AND outcome IS NOT NULL
            AND pnl_minor IS NOT NULL)
        OR
        (event_kind = 'CORRECTION'
            AND prior_event_id IS NOT NULL
            AND result_observation_id IS NOT NULL
            AND result_classification IS NOT NULL
            AND outcome IS NOT NULL
            AND pnl_minor IS NOT NULL)
        OR
        (event_kind = 'REVERSAL'
            AND prior_event_id IS NOT NULL
            AND outcome IS NULL
            AND pnl_minor IS NULL)
    )
);

CREATE UNIQUE INDEX uq_quantlab_corner_one_initial_settlement
    ON quantlab_corner_settlement_events (shadow_bet_id)
    WHERE event_kind IN ('NORMAL', 'LEGACY_BACKFILL');

CREATE INDEX idx_quantlab_corner_settlement_history
    ON quantlab_corner_settlement_events
    (shadow_bet_id, occurred_at DESC, corner_settlement_event_id DESC);

CREATE TRIGGER quantlab_corner_settlement_events_immutable
BEFORE UPDATE OR DELETE ON quantlab_corner_settlement_events
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

INSERT INTO quantlab_corner_settlement_events (
    corner_settlement_event_id,
    shadow_bet_id,
    fixture_id,
    event_kind,
    prior_event_id,
    result_observation_id,
    statistics_observation_id,
    result_classification,
    outcome,
    pnl_minor,
    occurred_at,
    settlement_rule_version,
    result_detail
)
SELECT
    'quantlab-corner-settlement-event-v1:' || encode(
        sha256(
            convert_to(
                q.shadow_bet_id || ':' || q.settled_at::TEXT || ':legacy-backfill',
                'UTF8'
            )
        ),
        'hex'
    ),
    q.shadow_bet_id,
    q.fixture_id,
    'LEGACY_BACKFILL',
    NULL,
    NULL,
    NULL,
    COALESCE(
        NULLIF(q.result_detail ->> 'result_classification', ''),
        'PLAYED_SETTLEABLE'
    ),
    q.outcome,
    q.pnl_minor,
    q.settled_at,
    COALESCE(
        NULLIF(q.result_detail ->> 'settlement_rule_version', ''),
        'CORNERLAB_TOTAL_CORNERS_HALF_LINE_SETTLEMENT_V1'
    ),
    q.result_detail
FROM quantlab_shadow_bets q
WHERE q.lab = 'CORNER'
  AND q.outcome IN ('WIN', 'LOSS', 'VOID')
  AND q.pnl_minor IS NOT NULL
  AND q.settled_at IS NOT NULL
  AND q.result_detail IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE FUNCTION reject_corner_shadow_settlement_mutation() RETURNS trigger AS $$
BEGIN
    IF OLD.lab = 'CORNER'
       AND (
           NEW.outcome IS DISTINCT FROM OLD.outcome
           OR NEW.pnl_minor IS DISTINCT FROM OLD.pnl_minor
           OR NEW.settled_at IS DISTINCT FROM OLD.settled_at
           OR NEW.result_detail IS DISTINCT FROM OLD.result_detail
       )
    THEN
        RAISE EXCEPTION 'CornerLab settlement state is append-only; write settlement events instead';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER quantlab_corner_shadow_settlement_columns_immutable
BEFORE UPDATE OF outcome, pnl_minor, settled_at, result_detail ON quantlab_shadow_bets
FOR EACH ROW EXECUTE FUNCTION reject_corner_shadow_settlement_mutation();
