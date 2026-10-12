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

## Rollout and proof of savings

The migration has not been applied to production. Railway's migration runner
executes migrations in one transaction, so these indexes are created without
`CONCURRENTLY`. The H2H table is relatively small, but index creation will
briefly lock writes to it during pre-deploy. Deploy during a quiet period.
Before and after deployment, compare the archive job duration, football
PostgreSQL CPU usage, and billed CPU dollars for several full days. Also check
that archive batches verify and mark hot-row deletion normally. There is no
defensible dollar savings claim until those observations are made.

Indexing this one query does not by itself establish the user's $30 monthly
total target. The two PostgreSQL services' current billed pace alone is near
that budget. Reaching it while retaining all football, basketball, and
QuantLab services may require changing their operating scope or hosting.
