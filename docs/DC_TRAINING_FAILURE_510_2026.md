# Dixon–Coles training failure: league 510, season 2026

## Evidence and cause

On 2026-10-14, Railway `sincere-balance` / `quantbet-engine` logged repeated
`DixonColesFitError: Optimizacija nije konvergirala: ABNORMAL:` for
`api-football:api-football:510:2026`, often about one minute apart. A read-only
database check found 248 attempts by 18:55 UTC, an existing active model pointer,
and a failed retrain status. The four scope components are provider, team ID
namespace, league, and season. Both first components correctly equal
`api-football`; this is not a duplicated provider value in storage.

The cached 2026 acquisition had 99 normalized matches (80 required), 18 teams,
at least 11 matches per team, dates 2026-07-31 through 2026-10-11, and a maximum
score of 8. The normalized data hash was
`494dde9505aaafa1351afab35b2f40093a5560a03137efb233959da8fb5d33fc`.
Normalization deduplicates identical fixture IDs and rejects conflicting
duplicates, missing fields, invalid scores, and non-FT results. Thus the observed
sample is not insufficient; a malformed raw acquisition is not indicated by this
failure. The sanitized score/date/team-pattern fixture is in
`tests/fixtures/dc_510_2026_sanitized.json`.

Replaying that cached sample with production settings reproduced optimizer status
2 (`ABNORMAL`) after 8 iterations: objective 275.8459 and infinity gradient norm
11.2874. Of 4,218 objective evaluations, 1,330 returned the flat `1e12`
sentinel because at least one Dixon–Coles correction was nonpositive under the
old ±0.20 rho bound. The flat region deprives finite-difference L-BFGS-B of a
useful direction. A continuous correction penalty and ±0.10 rho bound converged
on the sanitized sample. This is deterministic for the cached data and current
settings; the exact cause of every other failing league still requires its own
sample inspection.

The rapid repeat was a separate lifecycle defect. `mark_failed` set a six-hour
retry, but `refresh_inventory` changed scopes with old active pointers to `STALE`
and set `next_attempt_at` to the current time on every cycle. That erased the
failed-retrain backoff. The active pointer was not replaced by the failed fit.

## Behavior after this patch

The optimizer uses a continuous penalty and a narrower rho interval. It still
rejects nonconverged, nonfinite, or invalid-correction results. Activation follows
artifact and probability validation. Existing artifact JSON remains unchanged.

Failed retraining retains the active model. Optimizer retries for the same dataset
wait 1 hour, then 6 hours, then 24 hours. After three failures, a daily acquisition
check compares the normalized dataset SHA-256 and skips the expensive fit while
the dataset is unchanged. A changed dataset is fitted on that check and starts a
new failure streak if it fails. A changed training policy resets the streak and
queues retraining. Invalid input and other failures use a one-day retry. Each
scope has its own persisted state; one failed league does not stop the cycle's
other claimed scopes. Daily-window acquisition caching means newly completed
matches may not be visible until the next UTC training window.
The retry key tracks one failed dataset per target scope. A target whose current
and previous training seasons both fail for different datasets may still refit
one of them during a later retry; each failure remains bounded by the daily
schedule. A raw malformed provider response cannot be fingerprinted until it
passes strict normalization, so it is retried after one day.

## Railway validation after an approved deployment

1. Confirm `quantbet-engine` pre-deploy completed and migration
   `068_model_training_failure_fingerprint.sql` appears in `schema_migrations`.
   The service's `railway.json` runs `python -m h2h.migrate` before deployment.

   ```sql
   SELECT version, applied_at FROM schema_migrations
   WHERE version = '068_model_training_failure_fingerprint.sql';
   ```

2. In a read-only SQL session on the `sincere-balance` production Postgres,
   inspect the target row:

   ```sql
   SELECT provider, team_id_namespace, league_id, season, status,
          attempt_count, failure_streak, failed_dataset_sha256,
          next_attempt_at, active_model_version_id, active_generation,
          last_error_class
   FROM model_coverage_scopes
   WHERE provider = 'api-football' AND team_id_namespace = 'api-football'
     AND league_id = 510 AND season = 2026;
   ```

3. Read filtered engine logs with
   `railway logs -p c0aa8208-dd61-48c4-a1d8-488802e84f36 -e production -s quantbet-engine --since 2h --filter "model scope" --json`.
   Check `canonical_scope_id`/`model_scope`, dataset fingerprint and sample size,
   optimizer status/iterations/objective/gradient norm, classification, retry
   count/time, and previous active/fallback fields. A successful 510 fit should
   emit `model fit converged`, then `model scope activated` after validation.
4. If a fit fails, verify `active_model_version_id` and `active_generation` still
   identify the prior model and `next_attempt_at` stays in the future across
   several worker cycles. If the same dataset fails three times, confirm later
   logs classify it as `unchanged_dataset` and do not run an optimizer fit.
5. Inspect at least one other league/season row and its lifecycle logs to confirm
   its claim and activation proceed independently. Check opportunities continue
   to resolve existing active models during a retrain failure.

This validation uses no database reset and does not authorize a deployment.
