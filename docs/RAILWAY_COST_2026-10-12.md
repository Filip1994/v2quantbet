# Railway cost investigation (2026-10-12)

## Billed usage

Read from the authenticated Railway CLI for workspace `filip1994's Projects`.
The previous billing period (September 10 to October 10) used $33.51: $20.87
memory, $10.87 CPU, $1.41 volume, and $0.36 egress. The two PostgreSQL
services accounted for $15.62 (football) and $5.81 (basketball/baseball).
The football QuantLab dashboard cost $5.12, mostly CPU, during that period.

The current period started October 10. At approximately October 12 11:24 UTC,
usage was $3.31: $1.99 memory, $1.03 CPU, $0.20 volume, $0.05 backup, and
$0.04 egress. The football PostgreSQL service used $1.39 and the basketball
PostgreSQL service $1.04. Railway's early-cycle `estimatedBillDollars` was
$24.42, but the actual $3.31 spent in about 36 hours has a materially higher
simple 31-day run rate. Neither is a guaranteed invoice forecast.

## Measured database bottleneck

The football database currently holds 19 GB. `quantlab_market_observations`
alone occupies 13 GB and has about 8.6 million live rows. Its archive
maintenance `DELETE` was observed in `pg_stat_activity` for more than four
minutes while the database was doing file reads. Archive candidate selection
uses the same reference checks.

Migration `060a_quantlab_h2hlab_v1.sql` added the `quantlab_h2h_decisions`
table after the original archive reference indexes in migration 050. It did
not add indexes for `selected_observation_id` or `companion_observation_id`.
Production has about 33,000 H2H decision rows (69 MB). A read-only production
`EXPLAIN` of the archive's H2H reference predicate chose a sequential scan of
that table. The two partial indexes in migration 068 target exactly those
lookups. They do not change which observations may be archived or deleted.

## Production index application and proof of savings

At approximately 11:44 UTC on October 12, both indexes were created directly
in production in one short transaction. Both report `indisvalid = true` and
`indisready = true` and occupy about 3.2 MB each. A read-only `EXPLAIN` of the
same H2H reference predicate changed from a sequential scan to a `BitmapOr`
over the two new indexes. The index change did not alter archive row
eligibility, data, service cadence, or volume settings. An earlier concurrent-index attempt timed out
behind a long archive transaction and left an invalid index; that index was
removed before the successful application. No invalid index remains.
Within minutes, `pg_stat_user_indexes` reported more than 50,000 scans on
each new index, confirming the live workload is using them.

Migration 068 remains in the branch for durable schema history. Once merged,
its `IF NOT EXISTS` statements will see the live indexes and record the
migration version. Compare archive job duration, football PostgreSQL CPU usage,
and billed CPU dollars for several full days. Also check that archive batches
verify and mark hot-row deletion normally. There is no defensible dollar
savings claim until those observations are made.

## Service cadence changes

After the user chose a lower-cost schedule, the production Railway settings
were changed on October 12. `basketball-v2-worker` now runs at 05 minutes past
00, 06, 12, and 18 UTC instead of every five minutes. The football QuantLab
collector runs at 00, 06, 12, and 18 UTC instead of hourly. Its modeler runs
daily at 01:15 UTC instead of twice daily. The legacy basketball cold-storage
job runs every six hours instead of hourly. Both Basketball v2 and QuantLab
dashboards have Railway serverless mode enabled, so they may sleep when idle.
Football research, operations dashboard, engine, and PostgreSQL remain online.
The Basketball PostgreSQL service was briefly redeployed during this change
and is online with its original volume. Repository sources were reconnected
to the affected services so future changes remain deployable.

The current billing cycle's early estimate was $24.39 at about 12:10 UTC,
before a full day of the new schedule. It is not yet evidence that the $30
monthly target will be met. The workspace retains a $20 soft usage alert and
$40 hard usage limit. Compare daily spend for at least one full day after the
new cadence before making further changes.
