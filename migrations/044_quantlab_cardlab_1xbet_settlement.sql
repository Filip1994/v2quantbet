-- CardLab: 1xBet-only canonical card events and immutable settlement ledger.

CREATE TABLE quantlab_card_event_observations (
    card_event_observation_id TEXT PRIMARY KEY
        CHECK (card_event_observation_id ~ '^quantlab-card-events-v1:[0-9a-f]{64}$'),
    fixture_id TEXT NOT NULL
        REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    provider_fixture_id BIGINT NOT NULL CHECK (provider_fixture_id > 0),
    total_cards_1xbet INTEGER NOT NULL CHECK (total_cards_1xbet >= 0),
    qualifying_event_count INTEGER NOT NULL CHECK (qualifying_event_count >= 0),
    available_at TIMESTAMPTZ NOT NULL,
    settlement_rule_version TEXT NOT NULL
        CHECK (settlement_rule_version = 'CARDLAB_1XBET_TOTAL_CARDS_SETTLEMENT_V1'),
    event_payload JSONB NOT NULL,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quantlab_card_events_fixture_available
    ON quantlab_card_event_observations
    (fixture_id, available_at DESC, card_event_observation_id DESC);

CREATE TRIGGER quantlab_card_event_observations_immutable
BEFORE UPDATE OR DELETE ON quantlab_card_event_observations
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE TABLE quantlab_card_settlement_events (
    card_settlement_event_id TEXT PRIMARY KEY
        CHECK (card_settlement_event_id ~ '^quantlab-card-settlement-event-v1:[0-9a-f]{64}$'),
    shadow_bet_id TEXT NOT NULL
        REFERENCES quantlab_shadow_bets(shadow_bet_id) ON DELETE RESTRICT,
    fixture_id TEXT NOT NULL
        REFERENCES quantlab_fixtures(fixture_id) ON DELETE RESTRICT,
    fixture_observation_id TEXT NOT NULL
        REFERENCES quantlab_fixture_observations(fixture_observation_id) ON DELETE RESTRICT,
    card_event_observation_id TEXT
        REFERENCES quantlab_card_event_observations(card_event_observation_id) ON DELETE RESTRICT,
    outcome TEXT NOT NULL CHECK (outcome IN ('WIN', 'LOSS', 'VOID')),
    pnl_minor BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    settlement_rule_version TEXT NOT NULL
        CHECK (settlement_rule_version = 'CARDLAB_1XBET_TOTAL_CARDS_SETTLEMENT_V1'),
    result_detail JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (shadow_bet_id)
);

CREATE INDEX idx_quantlab_card_settlement_history
    ON quantlab_card_settlement_events
    (shadow_bet_id, occurred_at DESC, card_settlement_event_id DESC);

CREATE TRIGGER quantlab_card_settlement_events_immutable
BEFORE UPDATE OR DELETE ON quantlab_card_settlement_events
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE FUNCTION reject_card_shadow_settlement_mutation() RETURNS trigger AS $$
BEGIN
    IF OLD.lab = 'CARD'
       AND (
           NEW.outcome IS DISTINCT FROM OLD.outcome
           OR NEW.pnl_minor IS DISTINCT FROM OLD.pnl_minor
           OR NEW.settled_at IS DISTINCT FROM OLD.settled_at
           OR NEW.result_detail IS DISTINCT FROM OLD.result_detail
       )
    THEN
        RAISE EXCEPTION 'CardLab settlement state is append-only; write settlement events instead';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER quantlab_card_shadow_settlement_columns_immutable
BEFORE UPDATE OF outcome, pnl_minor, settled_at, result_detail ON quantlab_shadow_bets
FOR EACH ROW EXECUTE FUNCTION reject_card_shadow_settlement_mutation();
