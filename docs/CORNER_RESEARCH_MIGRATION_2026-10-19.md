# QuantLab retirement and Corner Research

Before: separate QuantLab UI + multi-lab collector/modeler, Research football UI,
KellyLab, and Production, sharing the football PostgreSQL database.

After: preserved CornerLab collection/model/settlement -> Research with exactly
two primary analytics tabs (Football Analytics and Corner Analytics) -> KellyLab
review. New Corner Research signals are database-enforced PAPER only. KellyLab
and Production code, configuration, formulas, sizing, and selected strategies are
not changed. Existing approved Corner Production intake remains the existing
strategy; this migration does not promote or activate any Research bucket.

## Data contract

`071_cornerlab_research.sql` adds a singleton activation timestamp and a registry
keyed by the original CornerLab shadow-bet ID. Existing records are HISTORICAL.
An AFTER INSERT trigger ingests new CornerLab source records atomically. A new
record is FORWARD only when its original decision and creation are both at or
after activation. Late imports stay HISTORICAL. Replaying an existing source
cannot duplicate ingestion. Settlement corrections and reversals are read from
the latest authoritative CornerLab event; no second settlement processor or
financial posting is introduced.

Both tabs use the same Research process and database. Football retains its
existing framework, drilldowns, historical records, and filters, adds isolated
analytics filters and table pagination, and keeps sparse multidimensional
cohorts as unranked audit rows. Ranked multidimensional cohorts require graded
N > 10; VOID is excluded from graded N. Corner uses the shared Research
`cohort_metrics` strategy metrics with source-stake-aware returns, calibration,
7/14/30-day and lifetime windows, league and multidimensional cohorts, line gaps,
expected/actual corners, distributions, drawdown, cumulative PnL and provenance.

PAPER is the source model's counterfactual ledger. PLAYED is an independently
selected read-only overlay of existing Production positions with the original
frozen production stake, price and latest operator state. Those two totals must
never be added. No cross-market matching by fixture alone is allowed.

The original CornerLab model grades full-match half-line totals. The stored
odds explorer preserves totals, team totals and handicaps, including quote IDs.
Handicap model probabilities and settlements are unavailable in the original
policy and are not fabricated. The explorer is bounded to stored series for 40
recent CornerLab fixtures and makes no external API calls.

## Runtime retirement

`h2h.cornerlab_entrypoint` hard-disables GoalLab, H2HLab and CardLab irrespective
of inherited enable flags and retains the existing collector advisory lock.
`h2h.cornerlab_modeler_entrypoint` does the same for offline fitting. The
collector keeps its six-hour schedule; the fitter keeps its daily schedule.
The duplicate collector remains disabled. After verification, the old QuantLab
UI is replaced by a database-free HTTP 308 compatibility redirect to Corner
Analytics. No database, volume, historical record or source implementation is
deleted.

The scheduled Corner fitter only fits/reuses the original model. Former verbose
offline historical holdout/audit pipelines remain preserved for manual use;
Research now supplies ongoing calibration and cohort analytics.

## Backup and restoration

Local backup directory:
`C:/Users/User/Documents/ChatGPT/fudbal/quantlab-retirement-backup-20261019`.

- `source.bundle` contains complete Git history and pre-migration service refs.
- `quantlab-source.zip` preserves all lab source and implementations.
- Branch `archive/quantlab-pre-retirement-20261019` and annotated tag
  `archive-quantlab-20261019` point to the deployed pre-retirement QuantLab UI.
- `railway-before.json` records source pins, config, schedules and deployment IDs.
- Manual Railway football backup `d7132078-a7ce-46de-8aee-34490508acc3`, volume
  instance `b9a01c7b-7fa7-45cf-a03f-2b13712fc52b`, was created before changes,
  has no expiration, and references the complete database volume.
- `critical/manifest.json` and compressed binary COPY exports preserve 13 core
  prediction, feature, settlement and financial tables. All were restored into
  an isolated local PostgreSQL schema and binary checksums/row counts matched;
  evidence is in `restore-evidence.json`. This is not a claim that the entire
  Railway volume was restored in a rehearsal.
- `integrity-before.json` freezes financial fingerprints and PLAYED history for
  before/after comparison. New legitimate appended records are excluded using
  the fixed baseline timestamp.

Restore source into a new directory with `git clone <backup>/source.bundle`,
then check out the appropriate archive branch. Never reset a shared checkout.
For an application rollback, reconnect each affected service to the exact
pre-migration commit/branch recorded in `railway-before.json`, restore its
start command/schedule, and redeploy the known-good build. Leave the additive
registry in place: it does not alter legacy readers or financial accounting.
Restore Research first, then worker configuration as required. Do not roll back
KellyLab or Production, which this migration does not deploy.

For disaster recovery, restore the Railway volume backup into an isolated
replacement database first, verify all ledgers and counts, then plan a controlled
switch. Never overwrite the live financial database with an older snapshot:
post-backup financial records must be retained and reconciled. Local binary
exports can be loaded with COPY BINARY into schema-compatible isolated tables;
`restore_critical.py` demonstrates the tested restoration and checksum procedure.

## Verification

The migration PostgreSQL test exercises historical backfill, late imports,
forward ingestion, source foreign-key protection, and database rejection of
PLAYED/execution activation. Analytics tests cover strict N, deduplication,
source isolation, windows, filters, pagination, production overlay stakes,
drawdown and HTML escaping. Production evidence is retained in the local backup
directory and the final report; do not mark production verified from deployment
SUCCESS alone.
