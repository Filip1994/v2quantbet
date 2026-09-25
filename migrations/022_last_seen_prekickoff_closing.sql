-- QuantBet Closing contract v2.
--
-- Canonical Closing is the latest valid same-series quote observed and captured
-- before kickoff. Freshness remains quality metadata and no longer vetoes a
-- real pre-kickoff price. Existing STALE_QUOTE finalizations are corrected
-- explicitly and auditable before the immutable trigger is restored.

CREATE TABLE pick_closing_contract_corrections (
    correction_id TEXT PRIMARY KEY CHECK (length(trim(correction_id)) > 0),
    pick_id TEXT NOT NULL UNIQUE CHECK (length(trim(pick_id)) > 0),
    finalization_id TEXT NOT NULL UNIQUE CHECK (length(trim(finalization_id)) > 0),
    prior_outcome TEXT NOT NULL CHECK (prior_outcome = 'STALE_QUOTE'),
    prior_closing_snapshot_id TEXT,
    corrected_closing_snapshot_id TEXT NOT NULL
        CHECK (length(trim(corrected_closing_snapshot_id)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    corrected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER pick_closing_contract_corrections_append_only
    BEFORE UPDATE OR DELETE ON pick_closing_contract_corrections
    FOR EACH ROW EXECUTE FUNCTION reject_pick_lifecycle_fact_mutation();

INSERT INTO pick_closing_contract_corrections (
    correction_id,
    pick_id,
    finalization_id,
    prior_outcome,
    prior_closing_snapshot_id,
    corrected_closing_snapshot_id,
    reason
)
SELECT
    'closing-contract-v2:' || f.finalization_id,
    f.pick_id,
    f.finalization_id,
    f.outcome,
    f.closing_snapshot_id,
    f.candidate_snapshot_id,
    'Closing contract v2: latest valid pre-kickoff same-series quote is Closing regardless of age.'
FROM pick_closing_finalizations f
WHERE f.outcome = 'STALE_QUOTE'
  AND f.candidate_snapshot_id IS NOT NULL
  AND f.closing_snapshot_id IS NULL
ON CONFLICT DO NOTHING;

-- This is a deliberate one-time historical correction. The migration records
-- every touched finalization above, temporarily removes the immutable guard,
-- performs the narrow state correction, and restores the guard in the same
-- migration transaction.
DROP TRIGGER pick_closing_finalizations_immutable ON pick_closing_finalizations;

UPDATE pick_closing_finalizations f
SET outcome = 'CAPTURED',
    closing_snapshot_id = f.candidate_snapshot_id
FROM pick_closing_contract_corrections correction
WHERE correction.finalization_id = f.finalization_id
  AND f.outcome = 'STALE_QUOTE'
  AND f.candidate_snapshot_id = correction.corrected_closing_snapshot_id
  AND f.closing_snapshot_id IS NULL;

CREATE TRIGGER pick_closing_finalizations_immutable
    BEFORE UPDATE OR DELETE ON pick_closing_finalizations
    FOR EACH ROW EXECUTE FUNCTION reject_pick_lifecycle_fact_mutation();

-- Settled picks whose CLV was previously unavailable solely because Closing was
-- marked stale can now receive the same immutable CLV fact the normal runtime
-- would have produced. Provenance and kickoff equality remain hard gates.
INSERT INTO pick_realized_clv (
    clv_fact_id,
    pick_id,
    settlement_event_id,
    closing_finalization_id,
    entry_snapshot_id,
    closing_snapshot_id,
    series_id,
    source,
    entry_odd_decimal,
    closing_odd_decimal,
    method_version,
    clv_ppm,
    realized_at
)
SELECT
    'pick-realized-clv-v1:' ||
        encode(sha256(convert_to(r.pick_id, 'UTF8')), 'hex'),
    r.pick_id,
    settlement.settlement_event_id,
    closing.finalization_id,
    settlement.entry_snapshot_id,
    closing.closing_snapshot_id,
    closing.series_id,
    closing.source,
    entry_quote.odd,
    closing_quote.odd,
    'CLV_ODDS_RATIO_PPM_V1',
    ROUND(((entry_quote.odd / closing_quote.odd) - 1) * 1000000)::bigint,
    CURRENT_TIMESTAMP
FROM pick_closing_contract_corrections correction
JOIN pick_closing_finalizations closing
    ON closing.finalization_id = correction.finalization_id
JOIN registered_picks r
    ON r.pick_id = closing.pick_id
JOIN value_evaluations evaluation
    ON evaluation.evaluation_id = r.evaluation_id
JOIN pick_settlement_events settlement
    ON settlement.pick_id = r.pick_id
   AND settlement.event_kind = 'NORMAL'
JOIN fixture_result_observations result
    ON result.result_observation_id = settlement.result_observation_id
JOIN quote_snapshots entry_quote
    ON entry_quote.snapshot_id = settlement.entry_snapshot_id
JOIN quote_snapshots closing_quote
    ON closing_quote.snapshot_id = closing.closing_snapshot_id
WHERE closing.outcome = 'CAPTURED'
  AND closing.cutoff_at = result.provider_kickoff_at
  AND closing.series_id = evaluation.selected_series_id
  AND closing.source = evaluation.source
  AND entry_quote.series_id = closing.series_id
  AND entry_quote.source = closing.source
  AND closing_quote.series_id = closing.series_id
  AND closing_quote.source = closing.source
  AND NOT EXISTS (
      SELECT 1
      FROM pick_realized_clv existing
      WHERE existing.pick_id = r.pick_id
  )
ON CONFLICT DO NOTHING;
