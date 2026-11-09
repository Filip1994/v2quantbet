-- Account for operator-triggered CornerLab provider calls without hiding them
-- from the shared football API quota or the Operations usage dashboard.
ALTER TABLE provider_request_usage
    DROP CONSTRAINT IF EXISTS provider_request_usage_category_check;

ALTER TABLE provider_request_usage
    ADD CONSTRAINT provider_request_usage_category_check CHECK (category IN (
        'discovery',
        'model_training',
        'opportunity_odds',
        'results_monitoring',
        'quantlab_context',
        'manual_corner_settlement'
    ));
