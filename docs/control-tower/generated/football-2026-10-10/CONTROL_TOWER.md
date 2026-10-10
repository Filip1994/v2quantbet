# QuantBet Control Tower V1

Snapshot: `2026-10-10T09:50:02Z`. Registered: **18**; detailed mapped: **8**; Git source ref: **15**; recognized module entrypoint: **8**. Registry coverage is 18/18; functional mapping coverage is 8/18.

Runtime metadata at that instant: **8** services with a `RUNNING` instance, **4** cron definitions, **1** latest `FAILED`/`CRASHED` deployments, **0** latest `SLEEPING` deployments. These counts overlap and are not a health score.

`SUCCESS` is the last deployment result, not uptime, job success or data freshness. `unknown` is preserved where evidence is missing. The historical [audit](../ARCHITECTURE_AUDIT_2026-10.md) gives context and direct links.

## Service registry

| Service / project | Purpose / owner | Code | Deployment / cron / data | Reads → writes | CI at commit | Risk | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `goallab-void-26a813a9b6`<br>`sincere-balance` / `055d5dd9-f8d6-443c-86e1-67b80357417c` | unknown / unknown | Filip1994/v2quantbet @ 6b937536; `unknown` | stopped_or_completed; deploy 2026-09-29T00:59:10Z; last observed SUCCESS deploy=2026-09-29T00:59:10Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | unknown → unknown | unknown | unknown | unknown; unknown |
| `quantbet-kellylab`<br>`sincere-balance` / `15a796eb-81b0-4b92-bd1a-c65b7272334d` | Read-only KellyLab shadow portfolio and allocation analysis / KellyLab | Filip1994/v2quantbet @ 8352f01a; `src/h2h/kellylab_dashboard_entrypoint.py` | running_instance; deploy 2026-10-10T00:45:21Z; last observed SUCCESS deploy=2026-10-10T00:45:21Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | football PostgreSQL: KellyLab shadow facts → none documented; DB grants unknown | success | medium_shared_database | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/src/h2h/kellylab_dashboard_entrypoint.py); inferred |
| `quantbet-kelly-tournament`<br>`sincere-balance` / `222072a1-56b3-4679-a61c-e30437ad70a0` | Kelly strategy tournament simulation; source and rationale unverified / unknown | unknown; `unknown` | running_instance; deploy 2026-10-10T01:05:30Z; last observed SUCCESS deploy=2026-10-10T01:05:30Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | unknown → unknown | unknown | unmapped_inline_runtime | unknown; inferred |
| `quantbet-research`<br>`sincere-balance` / `2965d3a3-49d1-4b16-a508-1becb6a9e3e1` | Display research signals and analytics separately from production picks / Football Research | Filip1994/v2quantbet @ 8352f01a; `src/h2h/research_dashboard_entrypoint.py` | running_instance; deploy 2026-10-10T00:45:22Z; last observed SUCCESS deploy=2026-10-10T00:45:22Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | football PostgreSQL: research signals → none documented; DB grants unknown | success | medium_shared_database | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/src/h2h/research_dashboard_entrypoint.py); inferred |
| `quantbet-engine`<br>`sincere-balance` / `3204398e-f9cc-49f7-8923-03e054cde348` | Discover fixtures, evaluate pre-match opportunities, register and settle paper picks / Football Production | Filip1994/v2quantbet @ 8352f01a; `src/h2h/entrypoint.py` | running_instance; deploy 2026-10-10T00:46:45Z; last observed SUCCESS deploy=2026-10-10T00:46:45Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | football PostgreSQL: fixtures, quotes, model state → football PostgreSQL: production decisions, picks, settlement | success | high_production_path | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/README.md); inferred |
| `quantbet-quantlab`<br>`sincere-balance` / `34662406-0e2b-448e-8bee-d8936d1e9998` | Read-only GoalLab, CornerLab, CardLab and H2HLab research dashboard / QuantLab | Filip1994/v2quantbet @ 34a52225; `src/h2h/quantlab_dashboard_entrypoint.py` | running_instance; deploy 2026-10-10T00:38:36Z; last observed SUCCESS deploy=2026-10-10T00:38:36Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | football PostgreSQL: quantlab_* shadow facts → none documented; DB grants unknown | unknown | medium_shared_database | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/ARCHITECTURE.md); inferred |
| `quantbet-quantlab-collector`<br>`sincere-balance` / `349ad868-2b0a-4192-a530-f9586dea202f` | Collect independent fixture, odds and context evidence for shadow labs / QuantLab shared core | Filip1994/v2quantbet @ 34a52225; `src/h2h/quantlab/collector_entrypoint.py` | scheduled_cron_current_run_unknown; deploy 2026-10-10T00:38:35Z; last observed SUCCESS deploy=2026-10-10T00:38:35Z (seen 2026-10-10T09:50:02Z); cron `0 * * * *` scheduled=yes, running now=no, last successful completion=unknown; data freshness=unknown | football PostgreSQL: immutable shared facts, quantlab_* watermarks → football PostgreSQL: quantlab_* observations | unknown | high_shared_provider_and_database | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/ARCHITECTURE.md); inferred |
| `quantbet-dashboard`<br>`sincere-balance` / `69a60980-686b-4156-a615-28b08ffd62c8` | Read-only production picks, accounting and operational dashboard / Football Production | Filip1994/v2quantbet @ 8352f01a; `src/h2h/dashboard_entrypoint.py` | running_instance; deploy 2026-10-10T00:46:45Z; last observed SUCCESS deploy=2026-10-10T00:46:45Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | football PostgreSQL: production facts → none documented; DB grants unknown | success | medium_sensitive_read_surface | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/README.md); inferred |
| `quantbet-void-1636701`<br>`sincere-balance` / `7845d562-640c-457a-9569-daf173e001a2` | unknown / unknown | Filip1994/v2quantbet @ a077d61c; `unknown` | failed_or_crashed_latest_deployment; deploy 2026-10-01T23:46:39Z; last observed SUCCESS deploy=unknown; data freshness=unknown | unknown → unknown | unknown | unknown | unknown; unknown |
| `quantbet-quantlab-modeler`<br>`sincere-balance` / `793608ac-2f9f-4cb1-b28c-a77f78a03a15` | Run offline/shadow model and audit cycles for enabled labs / QuantLab shared core | Filip1994/v2quantbet @ 34a52225; `src/h2h/quantlab/modeler_entrypoint.py` | scheduled_cron_current_run_unknown; deploy 2026-10-10T00:38:35Z; last observed SUCCESS deploy=2026-10-10T00:38:35Z (seen 2026-10-10T09:50:02Z); cron `15 */12 * * *` scheduled=yes, running now=no, last successful completion=unknown; data freshness=unknown | football PostgreSQL: quantlab_* observations → football PostgreSQL: quantlab_* model/decision state | unknown | medium_shadow_only | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/OPERATIONS.md); inferred |
| `Postgres`<br>`sincere-balance` / `8053c62b-2ba3-46e8-8bf0-bc5160cb6b9b` | Durable data store for services in its Railway project / Railway project | unknown; `unknown` | running_instance; deploy 2026-09-28T18:27:09Z; last observed SUCCESS deploy=2026-09-28T18:27:09Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | unknown → unknown | unknown | high_shared_state | unknown; inferred |
| `south-america-performance-query`<br>`sincere-balance` / `8d932c12-0b39-45db-9547-6fe2e72c751a` | unknown / unknown | unknown; `unknown` | stopped_or_completed; deploy 2026-10-10T00:30:09Z; last observed SUCCESS deploy=2026-10-10T00:30:09Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | unknown → unknown | unknown | unknown | unknown; unknown |
| `quantbet-void-1636701-ops`<br>`sincere-balance` / `9b6e43d2-5305-4c9f-bfee-6db8c5aa6fa1` | unknown / unknown | Filip1994/v2quantbet @ a3b26b4e; `unknown` | stopped_or_completed; deploy 2026-10-01T23:52:05Z; last observed SUCCESS deploy=2026-10-01T23:52:05Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | unknown → unknown | unknown | unknown | unknown; unknown |
| `quantbet-find-26a813a9b6`<br>`sincere-balance` / `9cd6573b-60bc-460b-850c-4e5dbf6755d8` | unknown / unknown | Filip1994/v2quantbet @ c6a54e23; `unknown` | stopped_or_completed; deploy 2026-10-09T23:38:39Z; last observed SUCCESS deploy=2026-10-09T23:38:39Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | unknown → unknown | unknown | unknown | unknown; unknown |
| `quantbet-find2-26a813a9b6`<br>`sincere-balance` / `d963a123-144d-4c05-80ee-f3e3a4a5e704` | unknown / unknown | Filip1994/v2quantbet @ 6b937536; `unknown` | stopped_or_completed; deploy 2026-09-29T00:59:10Z; last observed SUCCESS deploy=2026-09-29T00:59:10Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | unknown → unknown | unknown | unknown | unknown; unknown |
| `quantbet-quantlab-collector-ACut`<br>`sincere-balance` / `e0923ec8-22be-4d70-8f56-4aefc7add00b` | Alternate QuantLab collector; continued need unknown / unknown | Filip1994/v2quantbet @ 886af1ce; `src/h2h/quantlab/collector_entrypoint.py` | scheduled_cron_current_run_unknown; deploy 2026-10-04T02:05:23Z; last observed SUCCESS deploy=2026-10-04T02:05:23Z (seen 2026-10-10T09:50:02Z); cron `0 0 1 1 *` scheduled=yes, running now=no, last successful completion=unknown; data freshness=unknown | unknown → unknown | unknown | review_duplicate_candidate | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/OPERATIONS.md); inferred |
| `south-america-performance-query-v2`<br>`sincere-balance` / `eb56e80e-fc92-49b3-9671-1340a5b15f86` | unknown / unknown | Filip1994/v2quantbet @ 24366529; `unknown` | stopped_or_completed; deploy 2026-10-02T22:50:13Z; last observed SUCCESS deploy=2026-10-02T22:50:13Z (seen 2026-10-10T09:50:02Z); data freshness=unknown | unknown → unknown | unknown | unknown | unknown; unknown |
| `quantbet-archive-lifecycle`<br>`sincere-balance` / `fdb9a387-01ca-45c7-905e-bc7287ea97d4` | Apply documented cold archive lifecycle / Football storage | Filip1994/v2quantbet @ 39226ad5; `src/h2h/archive/lifecycle_entrypoint.py` | scheduled_cron_current_run_unknown; deploy 2026-10-09T21:07:19Z; last observed SUCCESS deploy=2026-10-09T21:07:19Z (seen 2026-10-10T09:50:02Z); cron `40 * * * *` scheduled=yes, running now=yes, last successful completion=unknown; data freshness=unknown | football PostgreSQL: archive eligible tables → football PostgreSQL: archive lifecycle state | unknown | high_data_retention_path | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/src/h2h/archive/lifecycle_entrypoint.py); inferred |

## Manually curated architecture scorecard

Scores are human assessments stored in `assessment.json`; the generator does **not** calculate or refresh them from live telemetry. The [audit rubric](../ARCHITECTURE_AUDIT_2026-10.md#ocena-arhitektonskih-oblasti) defines 1–10 bands. Missing runtime evidence remains `not assessed`.

| Dimension | Score / 10 | Confidence | Evidence |
| --- | ---: | --- | --- |
| Cohesion and modularity | 6 | medium | Separate production, research and QuantLab modules; shared repository |
| Coupling and shared state | 4 | high | 16 of 17 non-DB services share the Postgres superuser credential; 79 public tables are owned by postgres |
| Data lineage and temporal leakage | 6 | medium | available_at and append-only migrations 025–026; runtime samples unknown |
| Test coverage and reliability | 6 | medium | 151 test files and PR CI; coverage and flaky trend unknown |
| CI and release hygiene | 5 | high | PR CI exists; docs-only #243 merge triggered KellyLab production deployment; 14 of 15 linked services have build.watchPatterns, KellyLab has none; checkSuites=false |
| Rollback and recoverability | not assessed | low | PITR and HA disabled; Railway volume backup and schedule lists empty; external dump and restore exercise unverified |
| Observability and alerting | 5 | medium | Health/readiness and worker dashboard; alert delivery unknown |
| Incident handling | 4 | medium | Diagnostics exist; central owner/lifecycle record absent |
| Security and least privilege | not assessed | high | Only login role postgres is SUPERUSER/BYPASSRLS, owns all 79 public tables, and is shared by 16 of 17 non-DB services |
| DB migrations, backup and retention | not assessed | medium | Football PostgreSQL is 19.482 GB; PITR disabled, Railway volume backup and schedule lists empty; external backup and restore unverified |
| Runtime cost and API budgets | 5 | medium | Infrastructure period spent $33.22, estimated $33.49 at 19:37 UTC, hard cap $40; Agent cap is separate |
| Deploy complexity | 4 | high | 18 football Railway definitions; 4 cron; 3 without Git source ref in the 09:50 UTC fixture |
| Single points of failure | 4 | high | One football PostgreSQL service; Railway HA reported one member and isCluster=false; restore unverified |
| Scalability | not assessed | low | No load, queue-lag or saturation measurements |
| Maintainability | 5 | medium | Football change protocol and tests exist; diagnostic service ownership remains incomplete |
| Operational cognitive load | 3 | high | 18 football definitions in one project, including cron and one-shot diagnostics |

## Risk register

| ID | Risk | Severity × likelihood | Evidence | Action |
| --- | --- | ---: | --- | --- |
| R1 | Football services share a PostgreSQL superuser credential | 3 × 2 | Read-only comparison found 16/17 non-DB services share postgres; pg_roles confirms SUPERUSER and ownership of all 79 public tables | After verified backup/restore, test non-superuser Production, QuantLab and migration roles in isolation, then plan staged credential rotation |
| R2 | Many long-lived diagnostic definitions lack source ownership | 2 × 3 | Football 09:50 UTC fixture: 18 definitions, 3 without Git source ref; 8 mapped by strict owner/purpose/evidence/code criterion | Assign lifecycle/owner before any retirement proposal |
| R3 | Backup restore is not demonstrated | 3 × 2 | Football PostgreSQL PITR/HA disabled; Railway volume backup/schedule lists empty; external dump unknown; no isolated restore proof | Approve a cost-gated volume backup schedule, verify first snapshot, then separately review PITR and isolated restore drill |
| R4 | Collector fails after GoalLab history load and core captures are stale | 3 × 3 | 08:01 UTC run completed at 09:49; 11-19 UTC runs lack cycle completion; last confirmed core fixture/market capture 08:01 at the 16:53 SQL check; later query timed out; 0.750 GB RAM limit nearly reached in earlier 12-hour metrics | Review diagnostic PR #248, then after separately approved merge/deploy obtain exit/OOM reason and verify two full cycles plus DB freshness before choosing mitigation |
| R8 | Main merge triggers production deployment even for documentation-only changes | 2 × 3 | PR #243 merge SHA 4842946 matched KellyLab deployment with no build.watchPatterns; log recorded applied 0 migration(s) | Review and approve per-service build.watchPatterns, dependency matrix and rollback before merging #244 |

## Recent code history (metadata only)

Commit title describes what was submitted. It is not evidence of motive. `reason unknown` remains until a PR or decision document explicitly explains why.

| Repo | When (UTC) | What | Why |
| --- | --- | --- | --- |
| Filip1994/v2quantbet | 2026-10-10T00:38:45Z | [89d02523](https://github.com/Filip1994/v2quantbet/commit/89d0252324fcf55201b58b4987973f25414634f6) Test that unselected GoalLab cohorts keep analytics without Production highlight | reason unknown |
| Filip1994/v2quantbet | 2026-10-10T00:38:53Z | [d19629f4](https://github.com/Filip1994/v2quantbet/commit/d19629f4f00137e8d7f821078a8f85234c078f0b) Clarify GoalLab cohorts are unselected for Production, not retired | reason unknown |
| Filip1994/v2quantbet | 2026-10-10T00:38:59Z | [a3da222c](https://github.com/Filip1994/v2quantbet/commit/a3da222cc388c2fb0e7d1642a6a2f46e83c10d38) Describe GoalLab buckets as unselected, not retired | reason unknown |
| Filip1994/v2quantbet | 2026-10-10T00:39:04Z | [7b263afe](https://github.com/Filip1994/v2quantbet/commit/7b263afef098c41c6bff5eb0b214846b6b2b9d70) Rename GoalLab intake test to reflect unselected status | reason unknown |
| Filip1994/v2quantbet | 2026-10-10T00:45:19Z | [8352f01a](https://github.com/Filip1994/v2quantbet/commit/8352f01a9d00ecfcd6a58e95537660a59fa6df55) Production intake pilot: Research OU 2.5 at odds 1.81–2.00 | reason unknown |

## Recent pull requests

PR titles are metadata, not a verified explanation of intent. Open the linked discussion for rationale.

| Repo | PR | State | Documented reason in this snapshot |
| --- | --- | --- | --- |
| Filip1994/v2quantbet | [#238 Trigger FAW Championship retirement rollout](https://github.com/Filip1994/v2quantbet/pull/238) | closed | reason unknown |
| Filip1994/v2quantbet | [#239 Research: enforce retired odds exclusion on Active board](https://github.com/Filip1994/v2quantbet/pull/239) | closed | reason unknown |
| Filip1994/v2quantbet | [#240 Fix CI bootstrap: separate one-off settlement from schema migration 066](https://github.com/Filip1994/v2quantbet/pull/240) | closed | reason unknown |
| Filip1994/v2quantbet | [#241 Pilot Production intake: Research OU 2.5 at 1.81–2.00 only](https://github.com/Filip1994/v2quantbet/pull/241) | closed | reason unknown |
| Filip1994/v2quantbet | [#243 Issue #242 Phase A: evidence-based architecture audit](https://github.com/Filip1994/v2quantbet/pull/243) | open | reason unknown |

## Additional components

- **GoalLab** — Goal probability and shadow-pick experiments ([source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/GoalLab/README.md)); runtime status: shares QuantLab collector/modeler; switch value unverified.
- **CornerLab** — Corner probability and shadow-pick experiments ([source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/CornerLab/README.md)); runtime status: shares QuantLab collector/modeler; switch value unverified.
- **CardLab** — Card/foul probability and shadow-pick experiments ([source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/CardLab/README.md)); runtime status: documented disabled on 2026-10-04; current config unverified.
- **H2HLab** — Direct H2H research over read-only Dixon–Coles artifacts ([source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/H2HLab/README.md)); runtime status: shares QuantLab collector/modeler; switch value unverified.
