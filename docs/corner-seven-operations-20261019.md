# Corner Operations selection, 2026-10-19

The operator explicitly selected seven screenshot cubes. UNDER with graded N=13
is included; UNDER with N=12 is excluded. This is a fixed allowlist, never automatic
promotion from leaderboard rankings. Boundaries are [lower, upper).

|Selection|Odds|Model P|EV|Expected total minus line|Reference graded N|
|---|---|---|---|---|---|
|OVER|1.50–1.75|.65–.70|.10–.15|1–2|17|
|UNDER|1.75–2.00|.55–.60|0–.05|-1–0|13|
|OVER|2.00–2.25|.50–.55|.10–.15|0–1|20|
|OVER|2.00–2.25|.55–.60|.15–.20|0–1|14|
|OVER|2.00–2.25|.50–.55|0–.05|0–1|21|
|OVER|1.75–2.00|.55–.60|.05–.10|0–1|46|
|OVER|2.00–2.25|.50–.55|.05–.10|0–1|26|

`h2h.corner_buckets` defines all boundaries and exact predicates. Operations
and Research import those definitions. Research highlights measured lifetime
PAPER evidence over immutable source IDs; latest settlement wins, and multiple
source selections from the same fixture are preserved. The displayed historical
N is evidence, never a permanently hardcoded performance claim. Operations only
admits a selected cube while its current graded N is greater than ten.

Old C4/C5 definitions remain for historical provenance but are deselected from
new intake. The live Football allowlist remains BTTS NO odds 2.01–2.50 and OU OVER
odds 1.81–2.00. All three services use that same explicit environment allowlist.
Seven Corner cubes share first priority and are ranked by the existing measured
N/ROI score. Existing kickoff, bookmaker, exposure and stake gates apply.
Existing source-identity uniqueness and transaction locking prevent repeated
cloning. New Operations candidates remain PENDING until a human acts. This change
does not place bets, alter PLAYED positions, rewrite settlements or change Kelly.

Corner Analytics places seven highlighted rows above rolling analytics. Each
column supports ascending/descending sorting. Sort state is keyed by table,
preserves the current filters and page, and survives form submission. Selection
links open the exact source cube. Operations links go directly to Research.

## Backup and rollback

Local evidence: `C:/Users/User/Documents/ChatGPT/fudbal/corner-buckets-20261019`.
It contains the verified Git bundle, previous service configs and non-secret
allowlists, financial fingerprints, and the read-only production dry run.
The prior full archival workflow is in `quantlab-retirement-backup-20261019`.
No schema migration or financial record rewrite is necessary.

Restore the corresponding original `QUANTBET_PRODUCTION_INTAKE_BUCKETS` value
from `variables-before.json` with deployment skipped; then reconnect each service
to its original pinned source or roll back its previous successful deployment:

* Engine: `518bb04050161da6af084f391d3248caff368494`, deployment
  `deff86d8-f05d-47cf-95b1-b8c52bdc75b4`.
* Research: `bea8ebf110fd9864ae6bcc13be82fce45b9c29bc`, deployment
  `ad091623-ba18-4e8a-aec3-b844c0623e97`.
* Dashboard: `a50c3a0b54e6b99b4c00ec336d7f1587e320612c`, deployment
  `385da731-da73-4b8f-8109-3b4e4c1ada86`.

Archive refs: `archive/before-corner-seven-{engine,research,dashboard}-20261019`.
Never restore an entire old database over live accounting. Roll back code/config
only; preserve newly recorded source signals and financial events. Re-run the
read-only financial fingerprint comparison after deployment or rollback.
