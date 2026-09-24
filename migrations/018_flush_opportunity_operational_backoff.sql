-- One-time flush of opportunity-worker item retry state after provider-aware
-- freshness semantics were deployed. production_item_failures is mutable
-- operational scheduler state; no betting, quote, model, bankroll, or
-- settlement fact is changed. Any still-failing fixture is re-recorded by the
-- next bounded opportunity cycle with a new exponential backoff.

DELETE FROM production_item_failures
WHERE worker_name = 'opportunity';
