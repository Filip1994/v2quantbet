-- CardLab V6 raw-stat feature surface.
-- Preserve frozen V1/V2 snapshots while allowing the expanded raw-statistics payload.

ALTER TABLE quantlab_card_feature_snapshots
    DROP CONSTRAINT IF EXISTS quantlab_card_feature_snapshots_feature_version_check;

ALTER TABLE quantlab_card_feature_snapshots
    ADD CONSTRAINT quantlab_card_feature_snapshots_feature_version_check
    CHECK (feature_version IN ('CARDLAB_FEATURES_V1', 'CARDLAB_FEATURES_V2', 'CARDLAB_FEATURES_V3'));
