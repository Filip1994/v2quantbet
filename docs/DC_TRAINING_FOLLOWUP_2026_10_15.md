# Dixon-Coles training follow-up: sparse scopes and invalid corrections

## Production evidence

At 2026-10-15 01:43 UTC, `quantbet-engine` was healthy and other scopes were
activating (for example, 177/2026), but the reported failures were real. The
read-only production acquisition cache gave these reproducible observations:

| Scope | Accepted matches / teams | Original outcome | Root cause |
| --- | ---: | --- | --- |
| 3/2026 | 92 / 76 | evaluation limit, 15,092 evaluations | sparse per-team sample; 53 teams had fewer than 3 matches |
| 848/2026 | 230 / 153 | evaluation limit, 15,092 evaluations | sparse per-team sample; 83 teams had fewer than 3 matches |
| 731/2026 | 165 / 33 | optimizer reported success, but final DC correction was invalid | soft correction penalty allowed a positive `rho` near 0.097 |
| 388/2026 | 168 / 14 | numerical failure; the production run reported an invalid correction | optimizer searched near the correction boundary |
| 205/2026 | 101 / 35 | fit succeeded, but 60 of 1,190 possible ordered team pairs had invalid low-score corrections | final fit had `rho=0.1`; validation of a future pairing caught the issue |

The local replay used dates, scores, and remapped team IDs only. It made no
provider requests or production writes. The 510/2026 cached 99-match dataset
still converged on the regular path with valid corrections. Its production
retry was scheduled for 2026-10-15 02:31 UTC at the time of investigation.

## Correction

- Reject a production training sample before optimization when matches are
  fewer than twice the number of fitted teams. This catches the two reported
  high-dimensional, weakly covered scopes. It is recorded as insufficient
  data with the existing one-day retry and does not consume an optimizer fit.
- Keep the existing fit as the first attempt. Validate DC corrections for every
  distinct team pairing, including future pairings. If that fit fails or any
  correction is invalid, make one bounded second fit with `rho=0`. Zero is a
  valid nested model; the second fit must converge and pass the same all-pair
  validation before an artifact can be activated. If it fails, the original
  error is raised and the existing failure backoff applies.
- Version the algorithm as `production-dc-v3`. A v2-to-v3 version-only rollout
  retains active models and scheduled retry times while resetting failed-data
  streaks. Policy parameter changes still request retraining.

The fallback uses the already acquired dataset, so it makes no extra API
request. Existing artifact JSON and betting policy are unchanged. A failed
retrain retains the previous active pointer.

## Verification and risk

The sanitized 731, 388, and 205 datasets converged with `rho=0` and produced
finite normalized score matrices for every distinct team pairing. The normal
510 path still converged without fallback. Local tests: 1,416 passed, 63 skipped
because no local PostgreSQL test database was configured. The PostgreSQL CI
integration test covers the version-only rollout; CI must pass before merge.

For 205, the largest absolute market-probability difference between the old
fit and the fallback, across the 1,130 pairings where the old fit was usable,
was 0.02889. This measures output change, not calibration or profitability.
Newly activated scopes using `rho=0` need routine outcome monitoring. The
provider payload for 175/2026 still contains a malformed away score; it is
separately classified as invalid input and retried after one day.

## Railway checks after an approved deployment

1. Confirm the deployed engine commit, `/readyz` (`ready` and `schema_current`
   true), and zero consecutive `model_lifecycle` worker failures.
2. Inspect structured `model fit converged` logs for
   `optimizer_fallback="rho_zero"` on affected dense scopes, followed by
   `model scope activated`. Confirm no activation follows an unconverged fit.
3. Read `model_coverage_scopes` for 3, 848, 731, 388, 205, and 510. Sparse
   scopes should be `INSUFFICIENT_DATA` after their next eligible check; dense
   scopes should either activate valid artifacts or retain their previous
   pointers and bounded retry times. Confirm the 510 active pointer is intact.
4. Compare `attempt_count`, `failure_streak`, `failed_dataset_sha256`, and
   `next_attempt_at` across multiple worker cycles. Confirm no per-minute
   retries on unchanged data and no increase in `failure_streak` for skipped
   fits. Check at least one unrelated scope continues to activate.
5. Compare `provider_request_usage` for `model_training` before and after the
   checks. The fallback itself should not increase request count. Continue
   outcome monitoring for newly activated fallback models.
