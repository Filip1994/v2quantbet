-- Reset transient opportunity retry backoff created by the pre-provider-aware
-- freshness semantics. This table is operational scheduler state, not an
-- immutable betting/model fact. Genuine unavailable-odds failures are
-- immediately re-recorded by the worker and receive a fresh bounded backoff.

DELETE FROM production_item_failures
WHERE worker_name = 'opportunity'
  AND last_error_class = 'OpportunityOddsUnavailableError';
