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

Deployment is based on the currently live pinned source `72b781e`. Later universe
policy commits on the original service branch remain untouched and are not
silently activated by this cost deployment. They had an unrelated classification
reason test failure in the initial audit; the isolated live-code suites pass.

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

Rollback: reconnect Engine to `72b781e095ef1cbd03ace6a8c925514783bcff73` on its
original branch; Dashboard to `3d1d12d56cfaaa0ef99708a1d31ca487e79d8d91`.
Use previous successful deployment IDs in `services-before.json`. Restore
Postgres memory to 1 GB if tuning fails. Restart the retained redirect service
only if legacy navigation is restored. Never rerun financial repair scripts or
restore an old database over new accounting. Tournament must remain suspended.
