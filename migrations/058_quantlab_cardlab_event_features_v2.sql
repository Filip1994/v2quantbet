-- Preserve frozen V1 snapshots while allowing the event backed CardLab feature rule.
ALTER TABLE quantlab_card_feature_snapshots
    DROP CONSTRAINT quantlab_card_feature_snapshots_feature_version_check;

ALTER TABLE quantlab_card_feature_snapshots
    ADD CONSTRAINT quantlab_card_feature_snapshots_feature_version_check
    CHECK (feature_version IN ('CARDLAB_FEATURES_V1', 'CARDLAB_FEATURES_V2'));
