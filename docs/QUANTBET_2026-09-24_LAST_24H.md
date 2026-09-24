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


### Deploy-trigger efficiency finding

Both Railway services are sourced from `Filip1994/v2quantbet:main` and currently expose no path-scoped `watchPatterns` in service configuration.

Result: this documentation-only update triggered a fresh Railway deployment for both `quantbet-engine` and `quantbet-dashboard`.

This is not a correctness failure, but it is unnecessary build/deploy churn. The next infrastructure cleanup should define safe service-specific watch paths so changes under `docs/**` do not redeploy production code while code, migrations, dependency files, and service configuration still do.


---

## 9. Updates after the initial 06:19 CEST audit

The original 24-hour snapshot above ended at 06:19 CEST. The following same-day production work happened afterwards and is part of the continuing 2026-09-24 handoff.

### PR #37 — Seattle BTTS NO manual closing + Last observed timestamps

**Merge commit:** `2b52d6437413ea06827d4f87fa9a3e8ee803ce82`

- Added targeted migration `019_manual_close_seattle_btts_no.sql`.
- The migration selects the latest same-book quote that was both observed and captured before kickoff for the Seattle Sounders – Real Salt Lake **BTTS NO** pick.
- The override is append-only and explicitly tagged as operator/manual provenance.
- Quote history is not rewritten and the manual value is not represented as a true same-book closing fact.
- Dashboard History gained a visible Last observed timestamp.
- Production engine startup reported that one migration was applied, confirming migration 019 reached production.

### PR #38 — compact Last observed age

**Merge commit:** `25abc648c89f99ac3a928774db145a13288ed37c`

- Replaced the long visible UTC timestamp in the active Last observed box with a compact relative age such as `2h 36mins ago`.
- Exact UTC timestamp remains available in the HTML title/hover for auditability.
- Layout stays compact on mobile.

### PR #39 — subtle neon-yellow quote age

**Merge commit:** `06eb70a60089252089db30d3f9d09f4811e2ff0c`

- The compact Last observed relative age received a subtle neon-yellow text treatment.
- No glow, background, border, or box expansion was introduced.

### Monitoring investigation triggered by apparently stale quotes

Production screenshots showed provider observations several hours old. The investigation established an important distinction:

- the monitoring worker was still actively cycling;
- repeated `/odds` calls were visible in Railway logs;
- API-Football can return the same provider-published `update` timestamp on repeated polls;
- quote history intentionally deduplicates repeated observations with the same semantic identity.

Therefore an old **provider observation age** is not, by itself, proof that the QuantBet monitoring worker has stopped.

### PR #40 — monitoring freshness observability

**Merge commit:** `f9557dceeb01f4443b0d8997620d0f9bf5d424ae`

Changes in source:
- active dashboard distinguishes provider quote age from a separate `checked … ago` indicator;
- provider-request telemetry was extended with fixture/bookmaker/bet identity and provider update timestamp bounds;
- monitoring-cycle telemetry was extended with claimed/refreshed/persisted counts.

**Deployment nuance:** the dashboard part deployed successfully, but Railway marked the corresponding engine deployment as **SKIPPED**. Therefore the new engine-side telemetry from this PR must **not** yet be treated as live production evidence.

### PR #41 — correct meaning of `checked … ago`

**Merge commit:** `01ec4bdd156d88a3ad04df7b45c66c3b05c01e7f`

The first `checked` implementation incorrectly reused the capture time of the latest *new* quote snapshot. Because repeated identical provider observations are deduplicated, that could misleadingly show a very old check age.

This was corrected so the dashboard now uses:

`pick_monitoring_states.updated_at`

That timestamp advances when a pick is actually claimed for monitoring.

Current intended semantics:
- **neon-yellow age** = age of the provider-published quote observation;
- **gray checked age** = age of the latest monitoring claim/attempt.

This makes it possible to visually distinguish:
- a provider that has not published a new price;
- a QuantBet pick that truly has not been revisited by monitoring.

Production monitoring evidence around 12:30–12:59 CEST showed repeated monitoring cycles with two odds requests per bounded slice and `pending_work=true`. No concrete registered-pick starvation case was identified from those logs.

### PR #42 — model and market probabilities in History

**Merge commit:** `886c4c914baf2c22674309c95f44fe7b070f324f`

History now preserves the original decision context next to CLV:

- **Model** = QuantBet model probability at pick time;
- **Market fair** = bookmaker probability after de-vig;
- **CLV** remains a separate market-movement metric.

Raw implied probability was intentionally not duplicated into History. The de-vig / Market fair value is the direct comparator to model probability.

The resulting historical evaluation chain is:

`Model probability → Market fair probability → CLV → Result / P&L`

This is the preferred compact representation because it answers both:
1. **why the pick was taken**, and
2. **how the market moved afterwards**.

### Current monitoring interpretation

At the time of this update:
- no concrete stuck registered pick has been proven;
- monitoring keeps cycling and provider requests continue;
- `pending_work=true` indicates remaining bounded-slice work, not automatically starvation;
- provider observations can legitimately remain hours old if API-Football keeps returning the same published snapshot;
- any pick whose **checked age** materially lags the rest after PR #41 is a candidate for real monitoring starvation and should be investigated by pick ID.

### Scheduled follow-up

A one-time production quote-monitoring audit was scheduled for approximately **24 Sep 2026 18:51 CEST** to check:
- Last observed advancement per active pick;
- actual monitoring cadence;
- gaps between monitoring attempts;
- SAME_BOOK versus LIVE_PROXY provenance;
- stale/unavailable behavior;
- backlog/pending behavior;
- provider-data gaps versus software defects.

### Updated continuation priorities

1. Verify the 12-hour monitoring audit against each active pick.
2. Investigate any pick with abnormally old **checked age**, not merely old provider quote age.
3. Ensure the engine-side telemetry from PR #40 is actually deployed before using those new fields as production evidence.
4. Keep model probability, market fair probability, CLV, result and P/L together in History.
5. Preserve provider observation timestamps as authoritative; never fabricate freshness from polling time.
6. Continue investigating opportunity wall-budget overruns and sparse provider odds separately from registered-pick monitoring.


---

## 10. Opportunity qualification and provider-odds policy correction

### API-consumption audit

A production log sample covering roughly the late-morning / early-afternoon opportunity workload showed that the dominant API consumer was the **opportunity scanner**, not registered-pick monitoring.

In one sampled window:
- 161 `/odds` provider requests were observed;
- 4 fixture-date discovery requests were observed;
- approximately 128 preliminary opportunity refresh attempts were made;
- registered-pick monitoring was making approximately two odds requests per bounded slice.

The practical conclusion is that most odds-call pressure came from searching for new opportunities, especially on fixtures for which the provider returned no usable odds.

### PR #43 — repeated provider snapshots no longer block prediction

**Merge commit:** `74a8f3aca815a896dd6d9dd736db50a84933ca8c`

A correctness bug was found in the opportunity freshness boundary.

Before this fix:
1. the worker fetched a provider quote;
2. quote history correctly deduplicated an identical repeated provider observation;
3. the worker then required a local `captured_at` within 60 seconds as proof that the market had been returned in the current provider call;
4. deduplication meant that repeated provider observations retained the old local capture time;
5. a quote that had just been returned by API-Football could therefore be rejected before prediction/evaluation.

The fix now proves current-response membership directly from the canonical quotes returned by the current provider response and matches persisted state by exact:
- bookmaker;
- market;
- provider `observed_at`;
- source.

Immutable quote-history deduplication remains unchanged.

### Production proof after PR #43

After the fix reached the running engine, fixture `api-football:1510683` advanced through the opportunity funnel:

- predictions: 1;
- evaluations: 2;
- compared quotes: 2;
- odds unavailable: 0.

The candidate did not proceed to final quote refresh because the resulting evaluations did not qualify under the existing value policy. This is materially different from the prior zero-pick state: the model/value layer is now actually being reached.

No minimum EV, edge, odds-range, bankroll, or model-probability threshold was weakened by PR #43.

### Railway engine deployment gate issue

A separate infrastructure issue was identified during rollout.

The engine service had:
- path-scoped watch patterns configured for `src/h2h/**`, `migrations/**`, and `pyproject.toml`;
- GitHub source setting `checkSuites=true`.

The repository did not have a corresponding GitHub workflow/check-suite run for these commits, so Railway repeatedly created engine deployments and then marked them **SKIPPED**, while the dashboard deployed normally.

Because an old staged Railway environment patch could not be safely inspected, it was not blindly committed.

For the critical engine fixes, a manual service deployment of the exact `main` commit was used instead. This preserved service variables/configuration and bypassed the broken automatic check-suite gate.

### PR #45 — tolerate real but stale provider quotes

**Merge commit:** `7e4610d3b08ad3681fa4a8bd8862dc25d2066206`

The temporary API-Football-era execution policy was deliberately relaxed so that a genuine provider-published quote does not disappear from candidate evaluation merely because the provider has not refreshed it recently.

Current policy:

- **FRESH**: provider observation is within the strict 5-minute signal;
- **USABLE_STALE**: older than 5 minutes but no older than 8 hours;
- **STALE / hard-stale**: older than 8 hours.

`USABLE_STALE` quotes:
- remain explicitly marked as stale;
- retain the provider-published observation timestamp;
- may be used for model/value evaluation and pick registration;
- still require the existing model, edge and expected-value rules;
- no longer activate the accelerated stale retry loop;
- follow the normal kickoff-aware refresh cadence instead.

Quotes older than 8 hours remain ineligible for pick generation and retain bounded accelerated retry behavior.

### Migration 020

Migration `020_usable_stale_quote_state.sql` added `USABLE_STALE` to the durable quote-refresh state.

The production pre-deploy migration step reported:

`applied 1 migration(s)`

before the new engine container became healthy.

### Opportunity live-proxy veto removed

The stale-quote candidate path previously issued an additional live-odds call close to kickoff and could veto an otherwise qualifying stale-bookmaker pick.

That veto was removed from **opportunity qualification**.

Rationale for the current phase:
- the displayed bookmaker quote is still a real provider-published observation, not a fabricated price;
- the operator can manually mark/skip a pick if the offered price is no longer available;
- using the live proxy as a hard qualification gate created extra API consumption and contradicted this temporary operator-first stale-price policy.

The independent live closing / proxy-CLV pipeline remains intact; only the pick-generation veto was removed.

### Production verification of the new stale policy

The manually deployed PR #45 engine reached **SUCCESS** and acquired production leadership.

Two useful production cases were observed:

1. Fixture `api-football:1508557` initially returned a provider snapshot approximately 10h40m old. It remained correctly hard-stale under the new 8-hour ceiling:
   - predictions: 0;
   - hard-stale markets: 3;
   - no valid quote: 1.

2. Fixture `api-football:1510683` returned a provider observation approximately one hour old and was treated as usable stale:
   - predictions: 1;
   - evaluations: 2;
   - compared quotes: 2;
   - hard-stale markets: 0;
   - stale retries scheduled: 0;
   - prior stale retry state cleared: 1;
   - registered picks: 0 because the evaluations did not satisfy existing qualification rules.

This verifies that stale-but-usable quotes can now reach the real model/value funnel without creating accelerated retry pressure.

### Current remaining bottlenecks

1. **Provider coverage:** many fixture-specific odds calls still return no usable odds.
2. **Opportunity throughput:** the configured 30-second wall budget remains cooperative rather than a strict hard cutoff; observed cycles still exceed 30 seconds.
3. **API economics:** fixture-by-fixture opportunity odds discovery remains expensive and is the next major optimization target.
4. **Deployment automation:** the engine GitHub `checkSuites` gate still needs a clean committed Railway configuration fix; manual exact-commit deployment is currently the safe workaround.
5. **Provider strategy:** API-Football is adequate for the current validation phase but its slow quote publication cadence makes a second/faster odds source a likely future requirement.

### Post-deploy aggregate verification

Across the first three complete opportunity cycles after PR #45 acquired production leadership:

- due fixtures: 30;
- eligible fixture observations across slices: 37;
- preliminary provider refreshes: 3;
- odds unavailable: 1;
- quotes fetched: 14;
- predictions: 2;
- evaluations: 8;
- compared quotes: 8;
- usable/soft-stale markets evaluated: 4;
- hard-stale markets: 3;
- stale retries scheduled: 2, both from the hard-stale case;
- stale retry states cleared: 2;
- decisions: 0;
- registered picks: 0.

The two cycles containing usable-stale markets scheduled **zero** accelerated stale retries and still reached prediction/evaluation. The remaining zero-pick result in this short sample came after eight real value evaluations failed the existing qualification policy, not from a freshness pipeline blockage.

The opportunity wall-clock issue remains visible: all three sampled cycles exceeded the nominal 30-second cooperative budget (approximately 46s, 48s, and 93s).

### Updated current conclusion

The earlier observation of “no qualified picks” was partly misleading because a freshness/deduplication bug was preventing valid repeated provider snapshots from reaching prediction/evaluation.

That bug is fixed and live.

The opportunity funnel now reaches the model/value layer. Zero picks in an individual post-fix cycle can therefore be a legitimate result of the existing EV/edge rules, while provider no-odds responses and hard-stale data remain separate upstream constraints.



---

## 11. Value-layer, risk-cap and API retry audit — afternoon continuation

### PR #46 — structured opportunity rejection diagnostics

**Merge commit:** `a7ce4a3392e818a4716dc8a3f5b4d8c6b521c0ce`

Structured production logs were extended so a candidate that does not reach final quote verification now records:

- market and selection;
- preliminary odds;
- model-vs-market edge;
- expected value;
- rejection reason codes;
- final-quote decision context where applicable.

This was an observability-only change. No model, edge, EV, bankroll, staking or registration rule was altered.

### Production proof: qualified value candidates do exist

After PR #46 telemetry became active, fixture `api-football:1528647` produced multiple real value evaluations.

Two examples passed the model/value thresholds but were blocked by the risk layer:

1. **OU_25 OVER @ 1.85**
   - edge: **+8.14 percentage points**;
   - expected value: **+10.00%**;
   - rejection: `MAX_OPEN_EXPOSURE_EXCEEDED`.

2. **BTTS YES @ 1.67**
   - edge: **+7.01 percentage points**;
   - expected value: **+4.73%**;
   - rejection: `MAX_OPEN_EXPOSURE_EXCEEDED`.

Other evaluations from the same fixture included candidates that also failed minimum EV and/or minimum edge, but the two cases above demonstrate that the earlier impression of “no qualified picks” was incomplete.

**Current interpretation:** the opportunity freshness bug is no longer the primary blocker for these candidates. At least some valid model/value candidates are reaching registration eligibility and are then being stopped by the open-exposure risk cap.

The risk limit has **not** been relaxed. Changing max open exposure is a bankroll/risk policy decision and requires explicit operator approval.

### Representative production cycle with value evaluations

A production opportunity cycle around 13:19 UTC reported:

- due fixtures: 10;
- eligible fixtures: 13;
- preliminary refreshes: 5;
- odds unavailable: 4;
- predictions: 1;
- evaluations: 8;
- compared quotes: 8;
- hard-stale markets: 0;
- accelerated stale retries scheduled: 0;
- decisions: 0;
- registered picks: 0;
- duration: approximately 121 seconds.

The eight evaluations were real model/value work. Registration did not proceed because preliminary policy/risk rejection codes were present.

This is strong evidence that the stale-quote policy is no longer suppressing the funnel before the model/value layer.

### PR #47 — slower retry for fixtures with no provider odds

**Merge commit:** `225359ee2f5cde9e23fe54e72548fbaf7fb1dbde`

A separate API-economics problem was found in generic item-failure scheduling.

Before this change, `OpportunityOddsUnavailableError` inherited the generic transient-error retry sequence beginning at approximately:

`5s → 10s → 20s → 40s → ...`

That is too aggressive for a provider whose pre-match odds publication cadence is much slower.

Production evidence before the fix:

- 36 zero-odds calls in the sampled window;
- 29 unique zero-odds fixture IDs;
- repeated zero-odds fixture IDs included:
  - `1632432` ×3;
  - `1632433` ×3;
  - `1636700` ×3;
  - `1634027` ×2;
- some zero-odds fixtures were rechecked only about two minutes after the previous zero response.

The dedicated opportunity no-odds retry sequence is now:

`10m → 20m → 40m → 60m cap`

Generic transport/runtime failures retain the faster retry path.

The change does **not** affect:
- registered-pick monitoring;
- fixtures that already have usable odds;
- model probability;
- edge or EV thresholds;
- bankroll/risk rules;
- the 8-hour `USABLE_STALE` policy.

### PR #47 production rollout

The automatic Railway deployment for the merge was initially marked `SKIPPED` because of the engine source/check-suite deployment issue.

An exact-current-main engine deployment was then started manually through Railway. Deployment:

`cb14ffac-1390-4cb3-accc-b51e4003b449`

reached **SUCCESS** for commit `225359ee...`.

Initial post-deploy opportunity evidence showed:
- 28 eligible fixtures in one slice;
- 18 waiting for refresh rather than immediately re-polled;
- only a small due subset hitting the provider;
- cycle duration approximately 24 seconds in that sample.

A full recurrence proof requires observing the same zero-odds fixture IDs for at least the new 10-minute first-retry window. That longer verification is still pending at this checkpoint.

### PR #48 — expose the actual risk exposure snapshot

**Merge commit:** `fa955f18a7aca5a98815a2ff64cded33caffb26c`

To diagnose `MAX_OPEN_EXPOSURE_EXCEEDED` without changing the limit, registration logging now exposes:

- `open_exposure_minor`;
- `fixed_stake_minor`;
- `max_open_exposure_minor`;
- `available_bankroll_minor`.

This is diagnostics only.

Railway engine deployment `a72f9c17-b822-47a8-9a7b-fc4f53468941` reached **SUCCESS**. The next value candidate that hits the exposure gate will therefore reveal the exact live risk-cap numbers.

### Railway deployment automation status

The engine now has path-scoped watch patterns:

- `src/h2h/**`
- `migrations/**`
- `pyproject.toml`

This prevents documentation-only changes from being intended engine triggers.

However, a direct service-config read still reports:

`source.checkSuites = true`

even after Railway-agent attempts to set it false. This remains inconsistent with the intended deployment configuration and explains why some automatic engine deployments are still created and then marked `SKIPPED`.

Therefore:
- exact-commit manual engine deployment remains the verified fallback for critical fixes;
- the check-suite source setting must be considered unresolved until a direct service-config read reports the intended value.

### Risk-policy boundary

The repository development defaults are:

- fixed stake: 30,000 minor units;
- max open exposure: 300,000 minor units.

Those defaults would imply ten simultaneous full fixed-stake reservations, but **production variable values are hidden by Railway OAuth** and must not be assumed to equal repository defaults.

PR #48 was added specifically so the next live exposure rejection will provide authoritative production values.

### Current priorities after this checkpoint

1. Capture the first PR #48 exposure-cap log and record the exact production risk numbers.
2. Verify PR #47 by confirming zero-odds fixture IDs do not reappear inside the new 10-minute first-retry window.
3. Do not loosen `MAX_OPEN_EXPOSURE` without explicit operator approval.
4. Continue reducing fixture-by-fixture API cost; provider-level odds batching remains a promising next optimization.
5. Hard-enforce or better bound the opportunity 30-second wall budget; 120-second cycles still occur.
6. Resolve the Railway `checkSuites` deployment-gate inconsistency.
