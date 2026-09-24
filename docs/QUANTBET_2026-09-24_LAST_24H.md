# QuantBet — Last 24 Hours Engineering Log

**Document date:** 2026-09-24  
**Repository:** `Filip1994/v2quantbet`  
**Audit window:** 2026-09-23 06:19 CEST → 2026-09-24 06:19 CEST  
**Verified repository updates in window:** **92 commits**

> This document is a repository-grounded engineering log. It records every Git commit in the exact 24-hour window above, then consolidates the work into system-level milestones and the current continuation point.

---

## 1. Executive state

The last 24 hours materially changed QuantBet from a partially documented production pipeline into a much more operational system.

The dominant workstreams were:

1. **Production pick publication lifecycle**
   - rolling publication was finalized;
   - stale-quote retry behavior was corrected;
   - API budget policy was opened to the full 7,500-call daily provider capacity.

2. **Operations dashboard**
   - read-only dashboard shipped;
   - standalone dashboard service wiring was fixed;
   - intentional public dashboard access was supported;
   - odds monitoring and dashboard lifecycle presentation were simplified;
   - bookmaker identity, quote quality, pick history, and operator state became clearer and more auditable.

3. **Execution and operator workflow**
   - multi-bookmaker best-price execution was implemented;
   - operator state was expanded to explicit **PLAYED / SKIPPED** tracking;
   - dashboard write paths and timestamp serialization were fixed.

4. **Worker fairness and bounded execution**
   - monitoring refresh work was bounded into slices;
   - result settlement was bounded similarly;
   - pending work is exposed and fairly rescheduled;
   - long-running model fitting gained a wall-clock guard and cooperative abort path.

5. **Market identity and duplicate-risk protection**
   - API-Football market identity validation was hardened;
   - provider requests and monitoring were pinned to the exact canonical market;
   - fixture-level duplicate exposure was rejected;
   - candidate ordering now prioritizes expected value;
   - at most one registered pick per fixture is enforced.

6. **Closing price / CLV instrumentation**
   - live API-Football market close proxy capture was added;
   - proxy CLV is kept distinct from same-book CLV;
   - dashboard odds lifecycle was reduced to four meaningful checkpoints;
   - manual close corrections are auditable and bounded.

7. **Provider-aware opportunity freshness**
   - stale/final provider quote handling was redesigned around provider-published age;
   - exact market identity is part of freshness decisions;
   - near-kickoff stale quotes can be corroborated with the live market;
   - repeated provider observations are deterministically resolved;
   - stale retry backlog and operational backoff were reset/flushed after the migration;
   - non-ready fixtures are filtered before batch limiting;
   - opportunity cursor progress is preserved even when the wall-clock budget expires.

---

## 2. Most important architectural consequences

### 2.1 Exact-market identity is now a hard invariant

The worker no longer treats "odds for this fixture" as sufficient. The registered market series, provider bet identity, monitoring request, final verification, and freshness checks are tied to the **exact canonical market**.

This closes a major class of silent corruption where a quote could belong to the right match but the wrong market.

### 2.2 One fixture, one registered pick

The system now prevents duplicate fixture exposure and ranks candidates before registration. This means multiple qualifying selections on the same fixture cannot silently create correlated overexposure.

### 2.3 Runtime work is bounded

Monitoring, settlement, and model lifecycle work no longer get unlimited runtime inside one scheduler pass. Pending work is surfaced and rescheduled, and Dixon-Coles training is cooperatively abortable.

That protects the scheduler from a single expensive task monopolizing the worker.

### 2.4 Quote freshness is no longer a simplistic timestamp check

Freshness now considers provider-published age, exact market identity, and live-market corroboration near kickoff. This is materially safer than using a generic "latest record" rule.

### 2.5 CLV is becoming operationally auditable

The system now distinguishes:
- pick-entry odds,
- monitored/final same-book odds,
- live closing proxy,
- manual bounded close corrections.

That is the correct direction for post-pick evaluation because same-book closing evidence and proxy closing evidence are not treated as interchangeable.

---

## 3. Documentation drift found during this audit

`PROJECT_STATUS.md` is behind the actual repository state.

It still says that several layers are not finished end-to-end, including broader production execution, publication, monitoring, closing/CLV and dashboard work. The commit history in this 24-hour window proves that substantial portions of those layers now exist.

**Action:** project status documentation must be reconciled with the live code before it is used as the source of truth for future Codex work.

---

## 4. Continuation point

The correct next phase is **production verification and observability**, not another architecture rewrite.

Priority order:

1. **Verify main-branch CI / test status after commit `86652cd`.**
2. **Verify Railway production runtime** against the latest main commit.
3. **Inspect opportunity-worker diagnostics** after the provider-aware freshness migration:
   - ready vs deferred fixtures;
   - retry/backoff state;
   - cursor advancement;
   - wall-budget exhaustion behavior;
   - actual opportunity throughput.
4. **Verify live close proxy capture** around real kickoff windows.
5. **Verify one-pick-per-fixture behavior** on real multi-market candidate sets.
6. **Reconcile `PROJECT_STATUS.md` and `docs/PROGRESS.md`** with the implementation that now exists.
7. Only after the above is clean: move into **performance measurement / model-learning quality**, rather than adding more infrastructure.

---

## 5. Engineering rules to preserve

- Keep the architecture **mean and lean**.
- No broad refactor merely because the codebase grew.
- Exact fixture + exact market identity must fail closed.
- Runtime fairness matters more than maximizing work in one loop.
- Provider freshness must be evidence-based, not inferred from local observation time alone.
- One fixture should not create hidden correlated exposure.
- CLV sources must remain explicitly labeled by provenance.
- API capacity is available, but call volume should still be economically justified.
- Production behavior must be validated from logs/data, not assumed from green unit tests alone.

---

## 6. Full chronological commit log — every repository update in the 24-hour window

1. **24/09/2026 05:59:19 CEST** — `86652cd` — Preserve opportunity cursor progress on wall-budget exhaustion (#36)
2. **24/09/2026 05:50:36 CEST** — `01e73de` — Flush opportunity operational backoff after freshness migration (#33)
3. **24/09/2026 05:47:25 CEST** — `1981567` — Skip non-ready fixtures before opportunity batch limiting (#32)
4. **24/09/2026 05:40:36 CEST** — `33600ab` — Reset stale opportunity retry backlog after freshness fix (#31)
5. **24/09/2026 05:33:38 CEST** — `bdde5a9` — Make opportunity freshness provider-aware (#30)
6. **24/09/2026 05:32:05 CEST** — `b0ecf0d` — Restore opportunity flow with provider-aware odds freshness (#29)
7. **24/09/2026 05:02:46 CEST** — `07ec993` — Move finished picks into compact history (#28)
8. **24/09/2026 04:52:17 CEST** — `0b6bc51` — Simplify dashboard odds lifecycle and fix post-kickoff quality (#27)
9. **24/09/2026 04:29:47 CEST** — `00a16af` — Capture API-Football live market close proxy (#26)
10. **24/09/2026 03:53:52 CEST** — `47a9693` — Simplify dashboard quote quality status (#25)
11. **24/09/2026 03:32:15 CEST** — `5951877` — Separate live quote freshness from historical entry warnings (#24)
12. **24/09/2026 02:44:15 CEST** — `698bf60` — Clean bookmaker identity in dashboard odds UI (#23)
13. **24/09/2026 02:03:44 CEST** — `89e7a43` — Protect quote market identity and limit one pick per fixture (#22)
14. **24/09/2026 02:02:25 CEST** — `96445c0` — fix: rank single-book fixture candidates without provider metadata
15. **24/09/2026 02:01:05 CEST** — `ff97df9` — fix: apply fixture-level duplicate risk
16. **24/09/2026 02:00:54 CEST** — `0f30fd5` — fix: use fixture-level duplicate risk flag
17. **24/09/2026 01:59:51 CEST** — `8f76368` — fix: final-verify exact market and rank fixture values
18. **24/09/2026 01:59:34 CEST** — `df42540` — test: monitoring requests exact registered market
19. **24/09/2026 01:59:25 CEST** — `23b895a` — fix: pin monitoring to registered market series
20. **24/09/2026 01:59:06 CEST** — `18362af` — feat: monitor exact registered market
21. **24/09/2026 01:58:56 CEST** — `2072c8f` — feat: bind monitoring target to canonical market
22. **24/09/2026 01:58:50 CEST** — `00a20ea` — test: pin and cache exact provider bet type
23. **24/09/2026 01:58:40 CEST** — `6479033` — test: pin canonical market in provider request
24. **24/09/2026 01:58:30 CEST** — `27d23b3` — feat: pin provider requests to canonical market
25. **24/09/2026 01:58:20 CEST** — `6f6c565` — feat: allow exact market odds requests
26. **24/09/2026 01:58:11 CEST** — `e68f175` — feat: expose canonical API-Football bet mapping
27. **24/09/2026 01:56:38 CEST** — `bdd33ca` — test: enforce one registered pick per fixture
28. **24/09/2026 01:56:14 CEST** — `00f8e54` — feat: stop after first registered pick per fixture
29. **24/09/2026 01:56:05 CEST** — `9dc4555` — test: prefer strongest value on fixture
30. **24/09/2026 01:56:03 CEST** — `d885740` — feat: rank fixture candidates by expected value
31. **24/09/2026 01:55:13 CEST** — `5931ca4` — test: update duplicate fixture risk policy
32. **24/09/2026 01:55:10 CEST** — `530e75c` — feat: limit registration to one pick per fixture
33. **24/09/2026 01:55:07 CEST** — `680d2ef` — feat: reject duplicate fixture exposure
34. **24/09/2026 01:55:05 CEST** — `a2c01ab` — feat: enforce one pick per fixture
35. **24/09/2026 01:54:45 CEST** — `94cac57` — test: include provider bet identity
36. **24/09/2026 01:54:42 CEST** — `4f8dbed` — test: guard canonical market identity
37. **24/09/2026 01:54:03 CEST** — `1dccba1` — test: reject API-Football market identity mismatch
38. **24/09/2026 01:53:39 CEST** — `70e3aaa` — fix: validate API-Football market identity
39. **24/09/2026 01:28:32 CEST** — `3c9b91a` — Merge pull request #21 from Filip1994/fix/bounded-monitoring-results-slices
40. **24/09/2026 01:26:44 CEST** — `483878d` — test: cover bounded result settlement slices
41. **24/09/2026 01:26:25 CEST** — `aec6e26` — test: model pending worker flags in entrypoint fixture
42. **24/09/2026 01:26:22 CEST** — `e8c8654` — test: expose pending monitoring work
43. **24/09/2026 01:26:20 CEST** — `0dad3f6` — test: cover bounded monitoring slices
44. **24/09/2026 01:25:53 CEST** — `54d5fcf` — fix: fairly reschedule pending result work
45. **24/09/2026 01:25:51 CEST** — `26d5791` — feat: expose pending result work
46. **24/09/2026 01:25:48 CEST** — `0863636` — fix: bound result settlement scheduler slices
47. **24/09/2026 01:25:46 CEST** — `f4c01dc` — feat: support bounded result claims
48. **24/09/2026 01:25:14 CEST** — `9519521` — fix: fairly reschedule pending monitoring work
49. **24/09/2026 01:25:12 CEST** — `0f80a0e` — feat: expose pending monitoring slices
50. **24/09/2026 01:25:09 CEST** — `c992a25` — fix: bound monitoring refresh batches
51. **24/09/2026 01:25:07 CEST** — `8b0dd10` — feat: detect remaining due monitoring work
52. **24/09/2026 01:25:04 CEST** — `7aa5e7f` — feat: expose pending monitoring work boundary
53. **24/09/2026 01:14:55 CEST** — `a2febfd` — Merge pull request #20 from Filip1994/fix/model-lifecycle-wall-clock-guard
54. **24/09/2026 01:13:27 CEST** — `21122f4` — test: preserve existing trusted fit bridge contract
55. **24/09/2026 01:13:24 CEST** — `b7b5fc4` — test: exercise private guarded production fit path
56. **24/09/2026 01:13:22 CEST** — `3574908` — fix: keep guarded training on private quant path
57. **24/09/2026 01:13:20 CEST** — `c775672` — fix: preserve public quant fit API while guarding production fits
58. **24/09/2026 01:10:09 CEST** — `5585e4e` — test: keep scheduler progressing after model timeout
59. **24/09/2026 01:09:48 CEST** — `8742adb` — test: assert training bridge forwards abort guard
60. **24/09/2026 01:09:46 CEST** — `a219e32` — test: ensure model timeout returns scheduler control
61. **24/09/2026 01:09:43 CEST** — `452d9cd` — test: cover cooperative Dixon-Coles fit abort
62. **24/09/2026 01:08:59 CEST** — `7433bf8` — fix: enforce model lifecycle wall-clock guard
63. **24/09/2026 01:08:39 CEST** — `9e9eb92` — fix: expose cooperative abort guard to model trainer
64. **24/09/2026 01:08:37 CEST** — `e8b9003` — fix: propagate model fit abort guard through training bridge
65. **24/09/2026 01:08:21 CEST** — `6d10048` — fix: make Dixon-Coles fitting cooperatively abortable
66. **24/09/2026 00:24:10 CEST** — `356760a` — Serialize issue 15 dashboard write responses (#19)
67. **24/09/2026 00:21:59 CEST** — `426d7d5` — Serialize operator state timestamps in dashboard API
68. **24/09/2026 00:19:00 CEST** — `371e220` — Fix issue 15 standalone dashboard writes (#18)
69. **24/09/2026 00:16:49 CEST** — `f40983a` — Fix standalone dashboard operator state composition
70. **24/09/2026 00:05:35 CEST** — `66dccde` — Merge PR #17: PLAYED/SKIPPED operator tracking
71. **24/09/2026 00:04:07 CEST** — `03816cd` — Update PostgreSQL integration fixtures for operator state
72. **24/09/2026 00:00:57 CEST** — `3469664` — Add played and skipped operator tracking
73. **23/09/2026 21:13:45 CEST** — `084b654` — Merge PR #16: Multi-bookmaker best-price execution
74. **23/09/2026 21:13:03 CEST** — `0f5cab0` — Merge PR #13: Dashboard V1
75. **23/09/2026 21:02:54 CEST** — `719e50b` — Implement multi-bookmaker best-price execution
76. **23/09/2026 20:20:41 CEST** — `313b78b` — feat: support intentional public dashboard access
77. **23/09/2026 20:13:08 CEST** — `a682bd1` — fix: dispatch standalone dashboard service
78. **23/09/2026 18:56:23 CEST** — `9329361` — feat: complete read-only operations dashboard
79. **23/09/2026 18:13:35 CEST** — `52b5e94` — docs: reconcile progress with production pipeline
80. **23/09/2026 18:12:53 CEST** — `42ef825` — docs: align README with live production runtime
81. **23/09/2026 16:50:48 CEST** — `96bb0a9` — feat: add dashboard and fix pick odds monitoring
82. **23/09/2026 15:10:13 CEST** — `c2db102` — test: expect unrestricted provider budget categories
83. **23/09/2026 15:10:06 CEST** — `746127b` — config: expose full 7500-call provider budget
84. **23/09/2026 15:09:59 CEST** — `9b14e23` — config: allow full provider daily capacity
85. **23/09/2026 15:09:51 CEST** — `5930999` — config: remove internal API reserve
86. **23/09/2026 14:56:16 CEST** — `aa44379` — docs: record calibrated Kelly staking idea
87. **23/09/2026 14:42:27 CEST** — `4b58d8a` — Satisfy migration diff check (#10)
88. **23/09/2026 14:32:44 CEST** — `4acf8eb` — Finalize rolling QuantBet pick publication lifecycle (#9)
89. **23/09/2026 14:30:00 CEST** — `033a859` — feat: finalize rolling pick publication lifecycle
90. **23/09/2026 09:28:21 CEST** — `35bf683` — Prioritize due stale quote retries without starving normal work (#8)
91. **23/09/2026 08:59:17 CEST** — `0ce32d5` — Fix stale quote policy startup preflight wiring (#7)
92. **23/09/2026 08:51:10 CEST** — `ca5c196` — Fix freshness-aware stale quote refresh scheduling (#6)

---

## 7. Current head at document creation

- **Head commit:** `86652cd5211e2e08f72e671cfcb0fae52e322786`
- **Head message:** Preserve opportunity cursor progress on wall-budget exhaustion (#36)
- **Head timestamp:** 24/09/2026 05:59:19 CEST

This file should be treated as the handoff checkpoint for the next QuantBet work session.


---

## 8. Production verification performed after the 24h audit

### Railway runtime located

The active V2 runtime is in Railway project `sincere-balance`, with:
- `quantbet-engine`
- `quantbet-dashboard`
- `Postgres`

The separate Railway project `v2quantbet-deploy-picks` is not the active runtime; its only observed deployment was removed.

### Functional head deployment

Commit `86652cd` — **Preserve opportunity cursor progress on wall-budget exhaustion** — deployed successfully to both engine and dashboard before this documentation-only commit.

The engine acquired production leadership and continued cycling successfully.

### Live opportunity-worker evidence

Observed opportunity cycles after the freshness/cursor fixes show the worker is no longer stuck, but still has a material availability bottleneck.

Representative cycles:

- Cycle A:
  - due fixtures: 10
  - eligible fixtures: 13
  - odds unavailable: 8
  - processed fixtures: 0
  - budget exhausted: true
  - pending work: true

- Cycle B:
  - due fixtures: 10
  - eligible fixtures: 17
  - odds unavailable: 7
  - processed fixtures: 1
  - predictions: 1
  - decisions: 1
  - registered picks: 1
  - fresh quotes: 4
  - final refreshes: 1
  - budget exhausted: true
  - pending work: true

- Later cycle:
  - due fixtures: 10
  - eligible fixtures: 14
  - odds unavailable: 0
  - processed fixtures: 1
  - fresh quotes: 4
  - predictions: 1
  - stale retries scheduled: 1
  - budget exhausted: true
  - pending work: true

This confirms that the opportunity cursor/fairness path is progressing across cycles instead of repeatedly pinning the same first work slice.

### Provider freshness / final verification evidence

A live final-quote verification path was exercised. The worker emitted:

- mandatory final quote verification requested
- final quote verification used latest published provider snapshot

The cycle still produced a decision and registered one pick. The fallback is therefore operational in production rather than only unit-tested.

### Model lifecycle evidence

The model lifecycle is active and alternates between:
- model scope activated;
- model scope has insufficient data;
- one observed `DixonColesFitError` training failure.

The worker recovered and subsequent cycles continued successfully. This is not a scheduler crash, but the failure needs diagnostic attribution to the exact scope and fit condition before it can be classified as benign or defective.

### Immediate engineering focus from live evidence

1. **Investigate the repeated `opportunity odds unavailable` population** by fixture/provider/market rather than weakening freshness rules.
2. **Attribute the observed `DixonColesFitError`** to the exact model scope and error detail.
3. **Confirm API wall-budget economics.** Several opportunity cycles are reaching `budget_exhausted=true`; this is a per-cycle wall/work budget condition and must not be confused with the 7,500-call daily provider allowance.
4. **Observe the cursor for several more slices** to verify there is no starvation pattern in deferred fixtures.
5. **Reconcile status docs** only after production evidence is incorporated, so documentation does not overstate completeness.

### Current verified conclusion

The system is **running**, not merely built. The newest functional code is live and the worker survives sparse/no-odds cases, model-fit failures, stale-market refresh paths, and final-quote fallback without stopping the scheduler.

The current limiting problem is no longer basic orchestration. It is **quality and availability of actionable market evidence under bounded runtime**, plus better diagnostics for the remaining model-fit failure.
