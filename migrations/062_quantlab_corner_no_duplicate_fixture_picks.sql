-- CornerLab allows historical legacy duplicates to remain, but no new duplicate
-- exposure may ever be inserted for the same fixture.
--
-- Application code already serializes CornerLab inserts with the same advisory-lock
-- namespace. This trigger is the database backstop for any alternate/bypassing writer.

CREATE OR REPLACE FUNCTION reject_duplicate_corner_shadow_bet_insert()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended('quantlab:corner:' || NEW.fixture_id, 0)
    );

    IF EXISTS (
        SELECT 1
        FROM quantlab_shadow_bets q
        WHERE q.fixture_id = NEW.fixture_id
          AND q.lab = 'CORNER'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23505',
            MESSAGE = 'duplicate CornerLab fixture pick is not allowed',
            DETAIL = 'fixture_id=' || NEW.fixture_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS quantlab_corner_shadow_bets_insert_guard
ON quantlab_shadow_bets;

CREATE TRIGGER quantlab_corner_shadow_bets_insert_guard
BEFORE INSERT ON quantlab_shadow_bets
FOR EACH ROW
WHEN (NEW.lab = 'CORNER')
EXECUTE FUNCTION reject_duplicate_corner_shadow_bet_insert();
