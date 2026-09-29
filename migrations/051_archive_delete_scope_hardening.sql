-- Narrow archive-maintenance DELETE permission to market observations only.
-- All other QuantLab append-only tables keep the original unconditional mutation guard.

CREATE OR REPLACE FUNCTION quantlab_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'QuantLab observation/snapshot tables are append-only';
END;
$$;

CREATE OR REPLACE FUNCTION quantlab_market_observations_archive_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('quantbet.archive_maintenance', true) = 'on'
    THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'QuantLab market observations are append-only outside archive maintenance';
END;
$$;

DROP TRIGGER IF EXISTS quantlab_market_observations_immutable
    ON quantlab_market_observations;

CREATE TRIGGER quantlab_market_observations_immutable
BEFORE UPDATE OR DELETE ON quantlab_market_observations
FOR EACH ROW EXECUTE FUNCTION quantlab_market_observations_archive_guard();
