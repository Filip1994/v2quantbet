-- CornerLab shadow picks are permanent research evidence.
-- Selection policy may limit future exposure to one canonical pick per fixture, but
-- persisted CornerLab picks must never be physically deleted.

CREATE OR REPLACE FUNCTION reject_corner_shadow_bet_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'CornerLab shadow picks are append-only and cannot be deleted';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS quantlab_corner_shadow_bets_delete_guard ON quantlab_shadow_bets;

CREATE TRIGGER quantlab_corner_shadow_bets_delete_guard
BEFORE DELETE ON quantlab_shadow_bets
FOR EACH ROW
WHEN (OLD.lab = 'CORNER')
EXECUTE FUNCTION reject_corner_shadow_bet_delete();
