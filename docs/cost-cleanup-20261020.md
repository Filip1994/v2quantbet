# Cost cleanup, 20 October 2026 (Europe/Belgrade)

Operations previously queried GoalLab candidates and its entire graded history
on every intake cycle although no GoalLab bucket was active. Candidate and
historical reads now follow the source universes of the explicit selected bucket
specifications. Inactive sources execute no queries. Historical definitions/data
and explicitly selected-source behavior remain available. Current two Football
and seven Corner predicates, evidence, ordering, stakes, exposure and settlement
behavior are unchanged.

Production read-only comparison used one repeatable snapshot. Graded N and
selected candidates/order matched exactly. Floating ROI/score values matched to
1e-10 (unordered SQL floating accumulation already varies in its last digits).
Measured score-read round trip: 1,969 ms / 3 queries -> 750 ms / 2 queries. This is
a bounded query measurement, not a claim about total cloud savings.

Deployment preserves the actual live Engine source `a8a6044` and Dashboard
`bda84fc`, including their Serie A/Israel bans. Railway's service source pin
still showed older commits; deployment history revealed that the actual running
builds were newer. An initial build from the stale pin was replaced after this
was identified. Read-only audit found no newly cloned production picks during
that interval. The final branch merges preserve the existing policy; only a
pre-existing rejection-reason test was aligned to its blacklist precedence.

Backup/evidence directory:
`C:/Users/User/Documents/ChatGPT/fudbal/cost-cleanup-20261020`.
It contains verified Git bundle, previous service configurations, baseline
financial fingerprints, query comparison and raw billing/resource observations.
No financial records, database/volume, retention or API freshness policy changes.

Other authorized cleanup: Hub uses Research directly for Corner Analytics and
marks Goal/H2H/Card archived without waking legacy UI. Historical Corner links
open retained Research Corner history. Goal labels remain readable without a
retired-service link. After new Hub is verified, stop the obsolete QuantLab
redirect deployment and completed read-only temporary verifier. Retain their
service configuration and source archives for restoration.

Database memory tuning is a separate reversible service resource setting. Keep
existing CPU limit and volume untouched. Original memory limit: 1,000,000,000
bytes. Baseline cgroup showed approximately 770 MB of reclaimable inactive file
cache; shared/anonymous memory was below 250 MB. A 750 MB limit may reduce cache
cost, but must be reverted to 1 GB on OOM/restart, failed functional checks or
unacceptable query latency. Do not claim invoice savings before billing arrives.

Rollback: reconnect Engine to `a8a60445b3641c8cff538c21cc1640b22a816580` on its
original branch; Dashboard to `bda84fcc7a7b2fb083e6c94010118cd1bd0d24db`.
Use previous successful deployment IDs in `services-before.json`. Restore
Postgres memory to 1 GB if tuning fails. Restart the retained redirect service
only if legacy navigation is restored. Never rerun financial repair scripts or
restore an old database over new accounting. Tournament must remain suspended.
