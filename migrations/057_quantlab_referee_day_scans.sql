-- CardLab: durable progress for cross-competition referee-history discovery.
CREATE TABLE quantlab_referee_day_scans (
    scan_date DATE PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL,
    response_fixture_count INTEGER NOT NULL CHECK (response_fixture_count >= 0),
    referee_fixture_count INTEGER NOT NULL CHECK (referee_fixture_count >= 0),
    page_count INTEGER NOT NULL CHECK (page_count > 0)
);

CREATE TRIGGER quantlab_referee_day_scans_immutable
BEFORE UPDATE OR DELETE ON quantlab_referee_day_scans
FOR EACH ROW EXECUTE FUNCTION quantlab_reject_mutation();

CREATE INDEX idx_quantlab_context_referee_base_available
ON quantlab_fixture_context_observations
    (lower(btrim(split_part(referee, ',', 1))), available_at DESC)
WHERE referee IS NOT NULL;
