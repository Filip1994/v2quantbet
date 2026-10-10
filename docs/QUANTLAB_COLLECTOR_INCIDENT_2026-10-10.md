# QuantLab collector incident — football only

Issue [#247](https://github.com/Filip1994/v2quantbet/issues/247). Evidence below is read-only from Railway `sincere-balance` production and its PostgreSQL database on 2026-10-10. No restart, replay, resource change, deployment or database write was performed for this investigation.

## Observed facts

| Evidence | Observation |
| --- | --- |
| Last complete collector cycle | The 08:01 UTC cycle logged `QuantLab cycle completed` at 09:49:40 UTC, including Goal, Corner, Card and H2H work. |
| Subsequent cycles | The 11:01, 12:03, 13:02, 14:04, 15:02 and 16:03 UTC Railway deployments used the same application SHA `34a52225`; none logged a completed cycle. The 16:03 deployment `924be963-a368-48df-91b0-41331632f053` became `CRASHED` at 16:06:53 UTC. |
| Last stage in failed run | `GoalLab DC+ prepare stage=history_loaded rows=30000 elapsed_seconds=23.469` at 16:06:56 UTC; no later Python traceback or cycle-complete log is available. The predeploy migration reported `applied 0 migration(s)` and the application started. |
| Resource evidence | Collector memory limit is about 0.750 GB. The 12-hour sampled peak was 0.748 GB; the 16:03–16:08 30-second samples did not capture a near-limit value at termination. Railway diagnosis contains no exit reason. |
| PostgreSQL freshness at 16:53 UTC | `quantlab_market_captures`, fixture observations and discovery shards: 08:01:22 UTC. Goal picks: 08:06:27. Corner feature snapshots: 09:47:09. Card event observations: 08:01:22. H2H decisions: 08:01:22; H2H snapshots: 09:20:25. Goal decisions reached 15:04:18, but this is not a full collector cycle. Goal model versions reached 12:19:42 via the separate modeler. |

**Read-only follow-up:** the 17:01:24 UTC deployment `0d06f8e2-9315-48ad-8ebf-31b055f87ce4` on the same SHA was marked `CRASHED` at 17:04:20 UTC. Its last available log at 17:04:18 was again `GoalLab DC+ prepare stage=history_loaded rows=30000`; no `cycle completed` or Python traceback appears. This extends the observed pattern through 17 UTC without proving the termination cause. The 16:53 SQL watermarks above were not resampled for this follow-up.

The cron schedule is still firing and predeploy completed, so this is a runtime failure during collection/scoring rather than a disabled cron, failed build or failed migration. The modeler is a separate process and its success does not prove current collector ingestion. The four labs completed the 08:01 cycle; regular complete operation after it is unconfirmed. Historical fixture/statistics backfill exists, but a market quote at an uncollected instant cannot necessarily be reconstructed. Do not claim that all missed data is permanently lost or that all four labs remain fresh.

## Ranked explanations

1. **Memory exhaustion during approved GoalLab artifact preparation — high suspicion, unproven.** The process loads 30,000 historical rows with player payloads, then builds scoring context. The measured peak nearly reaches the limit. There is no OOM event or process exit code, and the 30-second metric can miss a short peak.
2. **Failure or stall in `goal_model_contract` or context parsing — possible.** The previous logs do not separate the artifact query, context construction and artifact deserialization. The new narrow diagnostic logs do so without changing results.
3. **Railway/container termination for another reason — possible.** The available deployment diagnosis provides no reason. Correlate future `CRASHED` timestamps with Railway events and the new stage/RSS logs.

The patch in this PR emits an artifact-query boundary, scoring-context start, one progress record per 2,000 rows and a sanitized exception class. It does not alter model inputs, probabilities, picks, writes or cron timing. An abrupt container kill still cannot produce an in-process exception log. The logs are designed to locate a future failure; they are not a claim of a proven fix. Existing CardLab shadow logs with `model_p=0.999999` warrant a separate calibration review outside this stabilization change.

**Confirmed, separate status bug fixed here:** `entrypoint.main()` previously logged a `runtime.run_once()` exception, then in one-shot mode logged `collector cycle complete` and returned successfully. Railway could therefore mark a Python-level failed cycle as successful. One-shot mode now re-raises the exception after logging it, so the process exits nonzero; the long-running dashboard mode retains its existing retry behavior. The new `test_collector_cycle_exit_status.py` exercises both successful and failing one-shot runs. This status fix does not explain the observed abrupt 16:06 crash, which produced no Python exception log.

## Review and release gate

The PR must remain draft. Test the diagnostic output and model parity offline. A merge to `main` may deploy several services that watch `src/h2h/quantlab/**`, not just the collector, so obtain explicit approval for the exact service/deployment list and maintenance window. Before any approved merge, save deployed SHA, service config and last known good cycle. After deployment, inspect the first two scheduled cycles for the last stage, RSS high-water mark, exit reason, all four lab counters and new fixture/market watermarks. If output changes or another watched service degrades, stop and restore its reviewed previous SHA under separate approval. Do not replay missed cycles or alter model parameters as part of this patch.
