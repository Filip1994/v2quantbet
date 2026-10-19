-- Additive migration. The authoritative CornerLab ledger and all financial tables
-- remain intact. Forward membership is fixed at first ingestion, never inferred
-- from settlement time or from a later feature/model rebuild.
CREATE TABLE research_corner_activation (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    contract_version TEXT NOT NULL DEFAULT 'CORNER_RESEARCH_V1'
);
INSERT INTO research_corner_activation(singleton) VALUES (TRUE);

CREATE TABLE research_corner_signals (
    source_shadow_bet_id TEXT PRIMARY KEY REFERENCES quantlab_shadow_bets(shadow_bet_id)
        ON DELETE RESTRICT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cohort TEXT NOT NULL CHECK (cohort IN ('HISTORICAL','FORWARD')),
    disposition TEXT NOT NULL DEFAULT 'PAPER' CHECK (disposition = 'PAPER'),
    execution_enabled BOOLEAN NOT NULL DEFAULT FALSE CHECK (NOT execution_enabled),
    strategy_version TEXT NOT NULL DEFAULT 'CORNER_RESEARCH_V1'
);

INSERT INTO research_corner_signals(source_shadow_bet_id,cohort)
SELECT shadow_bet_id,'HISTORICAL' FROM quantlab_shadow_bets WHERE lab='CORNER';

CREATE FUNCTION research_ingest_corner_signal() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.lab='CORNER' THEN
        INSERT INTO research_corner_signals(source_shadow_bet_id,cohort)
        SELECT NEW.shadow_bet_id,
            CASE WHEN NEW.decision_at >= a.activated_at
                 AND NEW.created_at >= a.activated_at THEN 'FORWARD' ELSE 'HISTORICAL' END
        FROM research_corner_activation a
        ON CONFLICT (source_shadow_bet_id) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER research_corner_ingestion AFTER INSERT ON quantlab_shadow_bets
FOR EACH ROW EXECUTE FUNCTION research_ingest_corner_signal();
