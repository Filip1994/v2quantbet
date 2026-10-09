# Issue #230: cost investigation and bounded change

## Production boundary

This branch was created from `origin/main` in an isolated worktree. No Railway
service, environment, database, schedule, variable, volume, deployment or
production branch was changed for this investigation. All database tests used a
temporary local PostgreSQL 17 cluster and synthetic fixtures.

## Seven-day Railway observations (2026-10-09)

The Railway metrics API returned 10,081 samples per service over 168 hours.
The table multiplies observed average GB by $10/GB-month and observed average
vCPU by $20/vCPU-month. These are *30-day run-rate estimates*, not invoice
charges; they omit storage, egress, other services and the Pro credit.

| Service | Average GB | Average vCPU | Compute run rate |
| --- | ---: | ---: | ---: |
| Football PostgreSQL | 0.950 | 0.290 | $15.30/month |
| Football engine | 0.129 | 0.059 | $2.47/month |
| Football Research | 0.081 | 0.0005 | $0.82/month |
| Football QuantLab dashboard | 0.195 | 0.0009 | $1.97/month |
| Football QuantLab collector | 0.646 | 0.031 | $7.08/month |
| Football QuantLab modeler | 0.659 | 0.083 | $8.25/month |
| Basketball/baseball PostgreSQL | 1.698 | 0.058 | $18.14/month |
| Basketball V2 worker | 0.465 | 0.048 | $5.62/month |

The two PostgreSQL services alone extrapolate to $33.44/month. The listed
services extrapolate to more than $59/month. A combined $30 invoice cannot be
asserted from these measurements. The Railway connector does not expose billed
GB-minutes/vCPU-minutes or the invoice, and the Railway web usage page required
a separate sign-in. Obtain the workspace usage breakdown before claiming
realized savings. Do not infer billed cost from configured memory ceilings.

The inventory showed 18 football services and 30 basketball/baseball services.
The main football PostgreSQL service was near its 1 GB memory limit; the
QuantLab collector reached about 0.75 GB. No limit reduction is proposed.
Baseball main and dashboard returned zero CPU and RAM samples during the
window; they were left intact. Some diagnostic/one-shot services have no cron
schedule, so their true cost must be checked in billed usage before any
service-level proposal.

## Change and equivalence boundary

`refresh_inventory()` formerly set `eligible = FALSE` on every
`model_coverage_scopes` row before re-enabling current scopes. The new query
changes only scopes that are currently eligible and have left the eligible
universe. The ensuing UPSERT and status refresh retain the same final
`eligible`, `updated_at`, policy, status, retry and model pointer values. The
fixture selection and canonical competition policy are unchanged.

On a local PostgreSQL replay with two current scopes, the second inventory
cycle performed four row updates instead of the previous six: two redundant
`TRUE -> FALSE` writes were removed. When one scope left the universe, it was
set to false exactly once. Repeated cycles did not rewrite an already false
scope. A paired baseline/candidate replay now compares every coverage scope
column, including timestamps, status, retry state and active model pointers,
after an empty universe, unchanged cycle, removal, return, policy change,
training claim, concurrent same-policy refreshes, activation and staleness.
The baseline substitutes only the former blanket-reset SQL; all other
repository code is shared. This establishes the tested database transitions,
not end-to-end pick or dashboard equivalence.

In a separate synthetic PostgreSQL 17 query microbenchmark with 1,000 already
current scopes and 12 alternating paired runs, the blanket reset's median
execution time was 3.897 ms and generated 218,492 WAL bytes (3,016 records).
The selective reset's median was 1.466 ms and generated zero WAL bytes for
that query. Each measured query ran inside a rolled-back savepoint. This
isolates the changed SQL only; the surrounding inventory still performs other
updates. The configured default lifecycle interval is 60 seconds, but the
deployed interval and actual call count have not been verified. No monthly
dollar estimate is defensible without production-equivalent call counts and
billed resource deltas.

## Validation

* `uv run --extra dev python -m pytest -q`: 1,299 passed, 63 skipped.
* Local PostgreSQL 17 integration:
  `QUANTBET_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55439/postgres`
  with `uv run --extra dev python -m pytest
  tests/integration/test_postgres_model_coverage_integration.py -q`:
  4 passed.
* The integration fixture now applies schema migrations 001-010 only. Later
  operator settlement migrations require real production evidence and cannot
  run in an empty temporary database. No production migrations were changed.

The production schema has no trigger or notification on
`model_coverage_scopes`. The replay has not exercised concurrent policy
changes or training retries/failures. It does not prove whole-system replay
equivalence for picks, settlement, ROI, Kelly allocations, archive payloads
and every dashboard. It must remain draft. The rollback for the proposed code
change is to revert its commit before any approved deployment; there is no
migration or data rewrite.

## Deferred candidates

Basketball V2 worker runs its stateful `schema.sql` migration on every five
minute cycle. Removing that call would skip release-gate repair blocks and is
not safe without versioning and a separate differential migration replay.
Likewise, no provider cadence, fixture scope, RAM limit, production schema or
service setting is proposed for reduction. The companion basketball draft
branch tests the unchanged-game UPSERT independently.
