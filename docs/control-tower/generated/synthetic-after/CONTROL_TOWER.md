# QuantBet Control Tower V1

Snapshot: `2026-10-02T00:00:00Z`. Registered: **3**; detailed mapped: **1**; Git source ref: **1**; recognized module entrypoint: **1**. Registry coverage is 3/3; functional mapping coverage is 1/3.

Runtime metadata at that instant: **1** services with a `RUNNING` instance, **0** cron definitions, **1** latest `FAILED`/`CRASHED` deployments, **0** latest `SLEEPING` deployments. These counts overlap and are not a health score.

`SUCCESS` is the last deployment result, not uptime, job success or data freshness. `unknown` is preserved where evidence is missing. The historical [audit](../ARCHITECTURE_AUDIT_2026-10.md) gives context and direct links.

## Service registry

| Service / project | Purpose / owner | Code | Deployment / cron / data | Reads → writes | CI at commit | Risk | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Postgres`<br>`example-football` / `database-example` | Durable data store for services in its Railway project / Railway project | unknown; `unknown` | running_instance; deploy 2026-09-30T22:00:00Z; last observed SUCCESS deploy=2026-09-30T22:00:00Z (seen 2026-10-02T00:00:00Z); data freshness=unknown | unknown → unknown | unknown | high_shared_state | unknown; inferred |
| `quantbet-engine`<br>`example-football` / `engine-example` | Discover fixtures, evaluate pre-match opportunities, register and settle paper picks / Football Production | Filip1994/v2quantbet @ bbbbbbbb; `src/h2h/entrypoint.py` | failed_or_crashed_latest_deployment; deploy 2026-10-01T23:00:00Z; last observed SUCCESS deploy=2026-09-30T23:00:00Z (seen 2026-10-01T00:00:00Z); data freshness=unknown | football PostgreSQL: fixtures, quotes, model state → football PostgreSQL: production decisions, picks, settlement | unknown | high_production_path | [source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/README.md); inferred |
| `example-new-service`<br>`example-football` / `new-example` | unknown / unknown | unknown; `unknown` | no_running_instance; deploy time unknown; last observed SUCCESS deploy=unknown; data freshness=unknown | unknown → unknown | unknown | unknown | unknown; unknown |

## Manually curated architecture scorecard

Scores are human assessments stored in `assessment.json`; the generator does **not** calculate or refresh them from live telemetry. The [audit rubric](../ARCHITECTURE_AUDIT_2026-10.md#ocena-arhitektonskih-oblasti) defines 1–10 bands. Missing runtime evidence remains `not assessed`.

| Dimension | Score / 10 | Confidence | Evidence |
| --- | ---: | --- | --- |
| Cohesion and modularity | 6 | medium | Separate production, research and QuantLab modules; shared repository |
| Coupling and shared state | 4 | high | Production engine and QuantLab collector resolve to the same DB host, database and credentials; DB grants unknown |
| Data lineage and temporal leakage | 6 | medium | available_at and append-only migrations 025–026; runtime samples unknown |
| Test coverage and reliability | 6 | medium | 151 test files and PR CI; coverage and flaky trend unknown |
| CI and release hygiene | 5 | high | PR CI and predeploy migrations; docs-only PR #243 merge triggered KellyLab production deploy; branch rules unknown |
| Rollback and recoverability | not assessed | low | No restore exercise, RPO or RTO evidence |
| Observability and alerting | 5 | medium | Health/readiness and worker dashboard; alert delivery unknown |
| Incident handling | 4 | medium | Diagnostics exist; central owner/lifecycle record absent |
| Security and least privilege | not assessed | medium | Production and QuantLab share DB credentials; effective grants and other access boundaries not inspected |
| DB migrations, backup and retention | not assessed | medium | 75 migration files; PITR disabled on both Railway PostgreSQL services; other backups and restore unverified |
| Runtime cost and API budgets | 5 | medium | Shared football envelope documented; measured usage and bill unknown |
| Deploy complexity | 4 | high | 48 Railway definitions, 14 cron, 17 without Git source ref |
| Single points of failure | 4 | high | One PostgreSQL definition per project; Railway HA status isCluster=false for both; restore unverified |
| Scalability | not assessed | low | No load, queue-lag or saturation measurements |
| Maintainability | 5 | medium | Change protocol and tests; Baseball documentation drift |
| Operational cognitive load | 3 | high | 48 definitions across two projects, including one-shot and cron |

## Risk register

| ID | Risk | Severity × likelihood | Evidence | Action |
| --- | --- | ---: | --- | --- |
| R1 | Football Production and QuantLab use the same DB credentials; effective grants unknown | 3 × 2 | Read-only Railway variable comparison 2026-10-10; values redacted | Read-only DB role/grant review, then propose separate credentials |
| R2 | Many long-lived diagnostic definitions lack source ownership | 2 × 3 | 48-service Railway fixture; 17 missing source refs | Assign lifecycle/owner before any retirement proposal |
| R3 | Backup restore is not demonstrated | 3 × 1 | Railway PITR disabled on both DBs; other backup and restore evidence absent | Confirm backup inventory, retention and isolated restore exercise |
| R4 | Deployment status may be mistaken for job or data health; Baseball cold storage later shows CRASHED | 2 × 3 | Two observed Railway fixtures show SUCCESS to CRASHED and cron instance drift | Review last job log/freshness; track process, job and data separately |
| R5 | Baseball README and PostgreSQL runtime contract diverge | 2 × 2 | quantbet-baseball README.md and src/quantbot/baseball/db.py | Update documentation in separate review |
| R6 | Older Basketball service points at a module absent from its source ref; v1/v2 coexistence lacks retirement evidence | 2 × 2 | Railway quantbet-basketball source/start module versus quantbet-baseball tree at ed2e1c4 | Confirm last successful run and consumers before proposing simplification |
| R7 | h2h documented workflows not present at reviewed HEAD | 1 × 2 | h2h README.md versus checked-out tree | Verify active scheduler and branch |
| R8 | Main merge triggers production deployment even for documentation-only changes | 2 × 3 | PR #243 merge SHA 4842946 matched KellyLab Railway deployment at 11:58 UTC | Require explicit deployment-impact approval before merging PR #244; review auto-deploy/watch configuration |

## Recent code history (metadata only)

Commit title describes what was submitted. It is not evidence of motive. `reason unknown` remains until a PR or decision document explicitly explains why.

| Repo | When (UTC) | What | Why |
| --- | --- | --- | --- |
| unknown | unknown | GitHub fixture unavailable | reason unknown |

## Recent pull requests

PR titles are metadata, not a verified explanation of intent. Open the linked discussion for rationale.

| Repo | PR | State | Documented reason in this snapshot |
| --- | --- | --- | --- |
| unknown | unknown | unknown | reason unknown |

## Additional components

- **GoalLab** — Goal probability and shadow-pick experiments ([source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/GoalLab/README.md)); runtime status: shares QuantLab collector/modeler; switch value unverified.
- **CornerLab** — Corner probability and shadow-pick experiments ([source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/CornerLab/README.md)); runtime status: shares QuantLab collector/modeler; switch value unverified.
- **CardLab** — Card/foul probability and shadow-pick experiments ([source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/CardLab/README.md)); runtime status: documented disabled on 2026-10-04; current config unverified.
- **H2HLab** — Direct H2H research over read-only Dixon–Coles artifacts ([source](https://github.com/Filip1994/v2quantbet/blob/8352f01a9d00ecfcd6a58e95537660a59fa6df55/QuantLab/H2HLab/README.md)); runtime status: shares QuantLab collector/modeler; switch value unverified.
- **h2h GitHub Actions paper-trading** — Separate football paper-trading repository; Railway mapping absent ([source](https://github.com/Filip1994/h2h/blob/b64fd507590a6d95ac0d3e56fd906f757fc79f5c/README.md)); runtime status: unknown; README workflow claims not verified at HEAD.
