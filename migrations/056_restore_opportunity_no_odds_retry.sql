-- Restore opportunity no-odds retry deadlines written under the temporary 4-hour throttle.
-- This touches only transient opportunity failure scheduling state; it does not modify
-- quotes, evaluations, picks, bankroll, exposure, or settlement data.

UPDATE production_item_failures
SET next_retry_at = LEAST(
    next_retry_at,
    last_failure_at + interval '1 hour',
    last_failure_at
        + (
            power(
                2,
                LEAST(GREATEST(failure_count - 1, 0), 3)
            ) * interval '10 minutes'
        )
)
WHERE worker_name = 'opportunity'
  AND last_error_class = 'OpportunityOddsUnavailableError'
  AND next_retry_at > LEAST(
      last_failure_at + interval '1 hour',
      last_failure_at
          + (
              power(
                  2,
                  LEAST(GREATEST(failure_count - 1, 0), 3)
              ) * interval '10 minutes'
          )
  );
