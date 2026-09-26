# QuantLab Work Log

This is the canonical chronological record of QuantLab implementation work.

## 2026-09-26 — Foundation and isolation

**Owner:** QuantLab core

### Completed

- Created separate Railway service `quantbet-quantlab`.
- Created three dashboard laboratories: GoalLab, CornerLab and CardLab.
- Added shared shadow-bet ledger `quantlab_shadow_bets`.
- Restricted initial bookmakers to Bet365 (8) and 1xBet (11).
- Added `quantlab_context` provider request category.
- Set QuantLab API budget target/hard ceiling to 1,000 requests/day at the QuantLab service boundary.
- Dashboard reports shadow bets, settled count, P&L, ROI, win rate, average CLV, max drawdown and QuantLab API usage.
- Blocked QuantLab from production write responsibilities by architecture.
- Refactored runtime ownership into `src/h2h/quantlab/`.
- Added top-level `QuantLab/` architecture documentation and separate GoalLab/CornerLab/CardLab specifications.

### API impact

Foundation itself adds no recurring provider calls. Future ingestion must use `quantlab_context`.

### Production impact

No production-model or bankroll/pick-registration behavior is changed by this refactor.

### Next implementation target

All-market Bet365 + 1xBet QuantLab ingestion, followed by CardLab v1 feature acquisition/derivation.

## 2026-09-26 — Next task frozen

**Owner:** QuantLab core

Created `QuantLab/TASKS/001_MARKET_COLLECTOR_CARDLAB_V1.md` as the canonical next implementation task. It covers Bet365/1xBet all-market ingestion, lab classification and CardLab v1 context features while preserving production isolation.


## 2026-09-26 — Task 001 implementation: market collector + CardLab v1

**Owner:** QuantLab core, CardLab, CornerLab and GoalLab scope policy

### Files/schema changed

Runtime additions/changes under the required boundary:

- src/h2h/quantlab/market_collector.py
- src/h2h/quantlab/market_classifier.py
- src/h2h/quantlab/provider.py
- src/h2h/quantlab/budget.py
- src/h2h/quantlab/runtime.py
- src/h2h/quantlab/scope.py
- src/h2h/quantlab/repository.py
- src/h2h/quantlab/dashboard.py
- src/h2h/quantlab/entrypoint.py
- src/h2h/quantlab/card_lab/context.py
- src/h2h/quantlab/card_lab/features.py
- src/h2h/quantlab/card_lab/rivalry.py
- migrations/025_quantlab_market_collector_cardlab_v1.sql
- tests/quantlab/test_task001.py

Documentation/contracts updated:

- QuantLab/ARCHITECTURE.md
- QuantLab/TASKS/001_MARKET_COLLECTOR_CARDLAB_V1.md
- QuantLab/CardLab/README.md
- QuantLab/CardLab/FEATURES_V1.md
- QuantLab/CornerLab/README.md
- QuantLab/GoalLab/README.md
- QuantLab/WORKLOG.md

### Implementation steps and decisions

1. Added MARKET_CLASSIFIER_V1. Market names are classified only for lab ownership:
   GOAL, CORNER, CARD or UNCLASSIFIED. No settlement semantics are inferred.
2. Added a QuantLab-only all-market parser. It intentionally does not call the production
   API-Football canonical adapter that only supports bet IDs 5 and 8.
3. The collector requests one /odds?fixture=<id> payload, filters only bookmaker IDs 8
   and 11 locally, and persists every valid returned selection including unsupported
   markets as raw UNCLASSIFIED observations.
4. Added append-only QuantLab tables for market observations, fixture context, completed
   match statistics, standings snapshots and CardLab feature snapshots. UPDATE/DELETE
   triggers reject mutation.
5. Extended PostgreSQLQuantLabRepository with QuantLab-owned writes and reads from shared
   immutable fixture/result facts. No production pick/value/bankroll write method was
   added.
6. Added a QuantLab API client whose provider requests execute under quantlab_context.
7. Added QuantLabRequestBudget. Configured capacity can be lower than 1,000 but can never
   exceed the hard 1,000/day ceiling.
8. Added a shared-provider safety stop: V1 defaults to a 7,500-call shared envelope and
   preserves 1,500 calls for production; QuantLab therefore stops when total shared usage
   reaches 6,000 even if its own allowance remains.
9. Added GOAL_SCOPE_V1 as a zero-request preflight gate. GoalLab remains broad but rejects
   youth U13-U23, academy/reserve/amateur competitions, Africa and the V1 Far East country
   registry before fixture-specific QuantLab spend.
10. Added CARDCORNER_STRONG_LEAGUES_V1. CardLab and CornerLab fixture-specific spend is
    restricted to a deterministic strong-league allowlist. Example: Poland Ekstraklasa is
    eligible; Poland III Liga is not.
11. Added API-Football fixture-context parsing for referee identity and timestamped raw
    provenance.
12. Added bounded historical CardLab context/statistics backfill only for strong-league
    fixtures. If referee identity is unavailable, /fixtures/statistics is not requested.
13. Added timestamped standings caching per league/season.
14. Implemented CARD_COUNT_RULE_V1 referee card rate with visible sample size and no
    shrinkage. Fouls use a separate sample size.
15. Implemented RIVALRY_REGISTRY_V1 as a deterministic registry. Uncovered pairs are
    UNKNOWN rather than false; no runtime LLM inference is permitted.
16. Implemented TABLE_PRESSURE_V1 from points-distance to title/promotion/playoff/
    continental/relegation thresholds, with persisted intermediate components.
17. Implemented MATCH_IMPORTANCE_V1 with frozen component weights and coverage-weight
    provenance for partial inputs.
18. Added hard leakage rejection: decision_at must precede kickoff and no feature input
    with available_at later than decision_at is accepted. Historical backfills do not
    retroactively become available for old decisions.
19. Extended CardLab dashboard with referee, card/foul rates, both sample sizes, rivalry,
    home/away pressure, importance, feature timestamp/version and provenance.
20. Added Task 001 tests for parser/raw retention, bookmaker filtering, one-response
    reuse, budget category/limits, production-write isolation, scope gating, leakage,
    referee exclusion, rivalry determinism, pressure, importance and dashboard provenance.

### Data sources/endpoints

- /odds?fixture=<id> — one all-market pre-match response per due fixture where practical.
- /fixtures?id=<id>&timezone=UTC — referee/fixture context for CardLab eligible fixtures.
- /fixtures/statistics?fixture=<id> — bounded completed-match card/foul history, only when
  referee coverage exists.
- /standings?league=<id>&season=<season> — cached table state for pressure/importance.
- Existing PostgreSQL fixtures, fixture_observations and fixture_result_observations are
  read as shared immutable facts.

All new provider requests use quantlab_context.

### API-cost impact

- GoalLab: at most one due fixture-level odds request after GOAL_SCOPE_V1 passes.
- CardLab/CornerLab: fixture-specific calls occur only after
  CARDCORNER_STRONG_LEAGUES_V1 passes.
- One odds payload feeds Bet365, 1xBet and every lab classifier.
- Standings are cached per league/season.
- Historical CardLab backfill is bounded per cycle and skips statistics when no referee
  is available.
- Hard QuantLab ceiling: 1,000/day.
- Shared-provider production reserve: 1,500/day by default.

### Leakage/provenance

Every CardLab component stores source, available_at, version, quality and intermediate
components. Snapshot persistence enforces available_at <= decision_at. Referee history
requires historical kickoff < decision_at and historical availability <= decision_at.
Target-match statistics are never queried for the target feature snapshot.

### Tests/verification

Unit/CI tests have been added. CI and Railway deployment verification are recorded in the
next work-log entry after completion.

### Production impact

**NONE.**

Production Dixon-Coles math, production market support, thresholds, pick registration,
bankroll/staking and Research Board behavior were not modified.


## 2026-09-26 — Task 001 verification and Railway activation

**Owner:** QuantLab core

### Verification steps completed

1. Ran GitHub CI repeatedly while implementing Task 001.
2. Fixed QuantLab lint issues without changing runtime semantics.
3. Updated stale integration expectations that directly followed from the previously-added
   quantlab_context category and the new latest migration
   025_quantlab_market_collector_cardlab_v1.sql.
4. The first full pytest run after QuantLab changes reached 991 passed / 7 failed. The
   remaining failures were stale production test fixtures/assertions, not changes in
   production runtime behavior. They were refreshed to match the already-current
   production contracts:
   - dashboard money formatting/current quote-age fixture;
   - entrypoint risk-exposure repository test double;
   - opportunity quote-object count;
   - existing Phase I Asia exclusion (J1 League);
   - bounded-worker monotonic-clock fixture/cursor expectation;
   - monitoring refresh-result test double.
5. No production application/runtime code was changed to make those tests pass.
6. Final GitHub Actions CI run 36210705470 passed lint and the complete pytest suite:
   **998 passed in 40.26s**.
7. Compared frozen Task 001 baseline commit 12ef71abc33931447be0fd448a6b6a7b11ec469e
   to the verified implementation head. Runtime changes are confined to
   src/h2h/quantlab/, migration 025, and the QuantLab compatibility shim; other changes
   are QuantLab documentation and test maintenance.

### Railway deployment verification

Service: quantbet-quantlab
Environment: production

Initial Task 001 deployments built and migrated successfully but failed health checks
because the QuantLab service did not yet have API_FOOTBALL_KEY.

Resolution:

- Added API_FOOTBALL_KEY to quantbet-quantlab as a Railway reference to the existing
  quantbet-engine API_FOOTBALL_KEY secret; the secret value was not copied into source
  code or documentation.
- Added QUANTBET_QUANTLAB_SHARED_PROVIDER_LIMIT=7500.
- Added QUANTBET_QUANTLAB_PRODUCTION_RESERVE=1500.

Verified runtime deployment:

- commit: e263026c93bf72f68692ff7908bf812cfd5785f7
- deployment: ae5c48c0-75de-420a-abd7-7162096899f7
- Railway status: SUCCESS
- production environment reports quantbet-engine, quantbet-dashboard,
  quantbet-research, quantbet-quantlab and PostgreSQL deployments as SUCCESS.
- deploy log shows QuantLab container startup and "QuantLab cycle completed" at
  2026-09-26T02:03:18.928618+00:00.
- latest pre-deploy reported 0 pending migrations, confirming migration 025 had already
  been applied by an earlier Task 001 deployment.
- one-hour QuantLab service metrics during verification were low and stable
  (CPU average about 0.021; memory average about 0.071 GB).

A read-only Railway Agent cross-check was attempted but the agent call timed out; no
mutation occurred. Final verification therefore uses direct Railway deployment, status,
logs, variables and metrics reads.

### API / safety verification

- QuantLab provider key is present only through Railway secret/reference configuration.
- All QuantLab provider calls remain quantlab_context.
- QuantLab hard ceiling remains 1,000 requests/day and cannot be raised by configuration.
- Shared-provider guard preserves the configured production reserve before allowing a
  QuantLab request.
- CardLab/CornerLab scope filtering occurs before fixture-specific provider calls.
- GoalLab scope filtering occurs before fixture-specific provider calls.
- Latest successful runtime cycle produced no logged exception.
- QuantLab remains shadow-only.

### Production impact

**NONE.**

No production Dixon-Coles implementation, production thresholds, production market
support, pick registration, bankroll/staking logic or Research Board runtime was changed
for Task 001.


## 2026-09-26 — Scope coverage correction: independent fixture discovery

**Owner:** QuantLab core

### Problem found after initial verification

The original Task 001 runtime correctly applied GOAL_SCOPE_V1 and
CARDCORNER_STRONG_LEAGUES_V1 before fixture-specific QuantLab calls, but it sourced the
upcoming fixture list from production `fixtures` / `fixture_observations`.

Production discovery intentionally applies a narrower Phase-I universe, including Asia,
cup and lower-tier exclusions. Therefore GoalLab could not actually observe some fixtures
that its own broader scope intended to admit. The local scope policy was correct, but the
upstream candidate inventory was too narrow.

### Correction

1. Added migration `026_quantlab_fixture_universe.sql`.
2. Added QuantLab-owned fixture identity table `quantlab_fixtures`.
3. Added append-only `quantlab_fixture_observations`.
4. Added append-only `quantlab_fixture_discovery_shards` so successful empty shards are
   cached and do not trigger repeated provider calls.
5. Existing QuantLab fixture foreign keys, including the shadow ledger, now target
   `quantlab_fixtures` rather than production `fixtures`.
6. Migration 026 seeds QuantLab fixture identity from existing API-Football production
   fixtures so previously collected QuantLab rows keep valid referential integrity.
7. Added global QuantLab date-shard acquisition through
   `/fixtures?date=<YYYY-MM-DD>&timezone=UTC`.
8. Date shards refresh every six hours by default and include one previous UTC day so
   recently completed fixtures can acquire final provider status for CardLab history.
9. The global shard is stored before lab filtering. GOAL_SCOPE_V1 and
   CARDCORNER_STRONG_LEAGUES_V1 are then applied locally before any fixture-specific
   `/odds`, `/fixtures?id`, `/fixtures/statistics` or `/standings` request.
10. Production fixture/result tables remain read-only historical fallback for legacy
    CardLab backfill; they no longer define the QuantLab upcoming universe.
11. Goal youth matching was hardened to U5-U23 plus youth/academy/reserve/amateur/
    junior/olympic aliases. Korea Republic / Republic of Korea were added to the explicit
    Far East aliases.

### API-cost impact

Global discovery is one API-Football call per UTC date shard, not one call per league.
With the default 36-hour lookahead, one-day lookback and six-hour refresh, the steady-state
discovery cost is bounded to only a few date-shard calls per refresh cycle. Fixture-specific
calls still occur only after the local lab scope gate.

The existing hard QuantLab ceiling of 1,000/day and shared-provider production reserve
remain unchanged.

### Tests added

- global fixture parser retains fixtures before scope filtering;
- runtime proves Poland III Liga can enter GoalLab while Japan and youth fixtures consume
  zero fixture-specific odds calls;
- fixture discovery persistence writes only `quantlab_*` tables;
- broader youth aliases and Korea Republic are rejected by GOAL_SCOPE_V1;
- integration latest-migration expectations now include migration 026.

### Production impact

**NONE.**

No production fixture discovery, model, odds adapter, pick registration, bankroll,
staking, Research Board or scheduler runtime was changed by this correction.


## 2026-09-26 — Fixture-universe correction verification

**Owner:** QuantLab core

### CI

GitHub Actions run 36220405108 passed:

- lint: PASS
- complete pytest suite: **1002 passed in 24.84s**
- PostgreSQL integration migrations include
  `026_quantlab_fixture_universe.sql`

### Railway

The first healthy runtime deployment containing migration 026, independent fixture
discovery, repository rewiring and the corrected scope file is:

- commit: `2877a3216d950e1166d40f13177273a067c19a7d`
- deployment: `e97bfefe-1b59-48ac-8c4d-8e14b8575e2e`
- service: `quantbet-quantlab`
- environment: production
- status: **SUCCESS**
- healthcheck: **SUCCESS**
- runtime log: `QuantLab cycle completed`

The runtime log also reported `QuantLab API hard ceiling reached; collection stopped for
UTC day`. This means the new global date-shard discovery could not spend another live
provider request during this verification window. That is the intended safety behavior:
the 1,000/day QuantLab hard ceiling was not bypassed for verification.

Because the schema check passed and the service started successfully, the new
`quantlab_fixtures`, `quantlab_fixture_observations` and
`quantlab_fixture_discovery_shards` tables are available to the running service.
The first live date-shard acquisition will occur after the next UTC daily provider-budget
reset, subject to the shared production-reserve guard.

### Isolation audit

The fixture-universe correction changes QuantLab-owned runtime, QuantLab migrations,
QuantLab documentation and tests only. Production Phase-I discovery remains unchanged and
is no longer authoritative for the QuantLab upcoming universe.

### Production impact

**NONE.**


## 2026-09-26 — Card/Corner Top-10 and API-spend correction

**Owner:** QuantLab core

### Trigger

Live review showed two operational problems:

1. broad GoalLab-eligible fixtures could persist CARD/CORNER rows because the fixture
   scope gate happened before one all-market odds response, while persistence did not
   re-apply lab ownership eligibility;
2. the 1,000/day QuantLab budget was exhausted before useful shadow output existed.

### Historical API diagnosis

Railway runtime evidence for 2026-09-26 UTC shows completed QuantLab cycles at
01:59:12, 01:59:40, 02:01:06, 02:03:19, 02:08:51 and 02:14:53, followed by the first
`QuantLab API hard ceiling reached` at 02:19:46.

The old runtime allowed up to 250 upcoming fixtures per cycle and refreshed odds every
900 seconds. Several code deploys also started replacement containers during the first
minutes. A successful odds response that produced zero stored market observations did
not leave any persistent refresh watermark, so such fixtures could become due again on
the next cycle/restart. Together, these mechanics explain the rapid budget burn.

Historical `provider_request_usage` stores only the aggregate
`quantlab_context` category, not endpoint-level counts. Therefore an exact retrospective
split of the 1,000 calls into odds/context/statistics/standings cannot be recovered from
the existing telemetry and must not be fabricated.

### Correction

- Replaced CARDCORNER_STRONG_LEAGUES_V1 with
  **CARDCORNER_TOP10_LEAGUES_V2**.
- CardLab/CornerLab are now limited to exactly:
  Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga,
  Belgian Pro League, Süper Lig and Scottish Premiership.
- Lower divisions, cups and UEFA club competitions are excluded from Card/Corner spend.
- Market persistence now receives an explicit allowed-lab set. Broad GoalLab-only
  fixtures store GOAL rows only; CARD/CORNER/UNCLASSIFIED rows require Top-10 eligibility.
- Added migration `027_quantlab_market_capture_watermark.sql` and
  `quantlab_market_captures`. Successful odds responses are watermarked even when they
  store zero rows, preventing empty-response re-poll loops across restarts.
- Default odds refresh changed from 15 minutes to 12 hours.
- Default standings refresh changed from 30 minutes to 6 hours.
- Automatic historical CardLab statistics backfill changed from 2/cycle to 0/cycle;
  future backfill must be separately budgeted.
- Runtime cycle logs now print discovered/backfilled/market/card counts directly in the
  visible message.

### Shadow-pick status

Task 001 created the shared `quantlab_shadow_bets` schema and dashboard reader but did
not implement any writer/decision engine for that table. Repository search confirms
there is no `INSERT INTO quantlab_shadow_bets` write path. Therefore the absence of
QuantLab picks is a missing next-stage strategy/pick-generation capability, not a
dashboard rendering failure.

### Production impact

**NONE.** Changes remain inside QuantLab runtime, QuantLab migrations, QuantLab tests and
QuantLab documentation. Production models, picks, bankroll and discovery are unchanged.


## 2026-09-26 — Top-10 league substitution: MLS for Scotland

**Owner:** QuantLab core

Per review, CARDCORNER_TOP10_LEAGUES_V2 keeps ten competitions but replaces Scottish
Premiership with Major League Soccer (MLS).

New CardLab/CornerLab Top-10 membership:

- Premier League
- La Liga
- Serie A
- Bundesliga
- Ligue 1
- Eredivisie
- Primeira Liga
- Belgian Pro League
- Süper Lig
- Major League Soccer (MLS)

Scottish Premiership is now outside the CardLab/CornerLab allowlist. GoalLab scope is
unchanged. No production model, pick, bankroll or discovery behavior is changed.


## 2026-09-26 — Task 002 implementation: GoalLab shadow pick engine

**Owner:** QuantLab core + GoalLab

### Objective

Convert already-persisted QuantLab fixtures and GOAL market observations into auditable
shadow-only GoalLab decisions and expose the upcoming fixture/decision pipeline in the
QuantLab dashboard.

### Files/schema changed

- `migrations/028_quantlab_goal_shadow_engine.sql`
- `src/h2h/quantlab/goal_lab/shadow_engine.py`
- `src/h2h/quantlab/repository.py`
- `src/h2h/quantlab/runtime.py`
- `src/h2h/quantlab/entrypoint.py`
- `src/h2h/quantlab/dashboard.py`
- `tests/quantlab/test_task002.py`
- QuantLab docs and integration latest-migration expectations

### Implementation

1. Added append-only `quantlab_goal_decisions` for both PICK and PASS evidence.
2. Added `GOALLAB_SHADOW_POLICY_V1`.
3. GoalLab resolves the existing validated active API-Football Dixon-Coles artifact for
   the exact league/season as a read-only control model. It does not train or activate
   production model state.
4. Canonical Task 002 evaluation is intentionally limited to complete same-capture,
   same-bookmaker two-way markets:
   - provider bet 5: O/U 2.5 OVER/UNDER;
   - provider bet 8: BTTS YES/NO.
5. Two-way proportional de-vig computes market probability. Edge and EV are recorded from
   the selected model probability.
6. Explicit PASS reasons cover no active model, missing team coverage, missing complete
   market, stale/future quote, kickoff too close, odds outside range, edge below minimum,
   EV below minimum and better price available.
7. Default experiment thresholds are edge >= 3pp, EV >= 3%, odds 1.40–4.00, quote age
   <= 13h, kickoff > 15m, flat shadow stake 10,000 minor units.
8. Only the best qualifying bookmaker price per market/selection/evidence cycle is a PICK.
9. Only PICK decisions write to `quantlab_shadow_bets`.
10. Deterministic decision/shadow IDs make repeated cycles over unchanged evidence
    idempotent.
11. Goal shadow evaluation runs after collection and remains active when provider
    collection is stopped by the daily API ceiling.
12. GoalLab dashboard now includes an upcoming fixture/decision pipeline showing scope,
    market capture, PICK/PASS reason, model and candidate value.

### API-cost impact

**Zero new API-Football endpoints and zero additional provider requests.** Task 002 uses
persisted QuantLab market observations and read-only production model artifacts.

### Leakage / provenance

All selected market observations must have `captured_at <= decision_at < kickoff_at`.
The exact immutable model version and market observation IDs are persisted in decision
evidence. No result/post-kickoff data is used in the decision stage.

### Production impact

**NONE.** Task 002 does not write production quotes, value evaluations, pick decisions,
registered picks, bankroll, model versions or active model pointers.


## 2026-09-26 — Task 002 implementation: GoalLab shadow pick engine

**Owner:** QuantLab core + GoalLab

### Files/schema changed

- `src/h2h/quantlab/goal_lab/shadow_engine.py`
- `src/h2h/quantlab/repository.py`
- `src/h2h/quantlab/runtime.py`
- `src/h2h/quantlab/entrypoint.py`
- `src/h2h/quantlab/dashboard.py`
- `migrations/028_quantlab_goal_shadow_engine.sql`
- `tests/quantlab/test_task002.py`
- `tests/api/test_quantlab_dashboard.py`
- integration latest-migration assertions
- `QuantLab/TASKS/002_GOALLAB_SHADOW_PICK_ENGINE.md`
- `QuantLab/ARCHITECTURE.md`
- `QuantLab/GoalLab/README.md`

### What changed

1. Added `GOALLAB_SHADOW_POLICY_V1`, the first real QuantLab PASS/PICK decision engine.
2. GoalLab uses the existing validated active Dixon-Coles artifact for the exact
   API-Football league/season as a **read-only control model**. QuantLab does not retrain,
   activate or mutate production model state.
3. V1 supports only complete two-sided canonical goal markets:
   - provider bet 5: O/U 2.5 OVER/UNDER;
   - provider bet 8: BTTS YES/NO.
4. Market fair probability uses proportional two-way de-vig:
   `(1/selected_odds) / ((1/selected_odds) + (1/companion_odds))`.
5. V1 shadow gates are frozen at:
   - minimum edge 3 percentage points;
   - minimum EV 3%;
   - odds 1.40 to 4.00;
   - maximum quote age 13 hours;
   - at least 15 minutes to kickoff;
   - flat shadow stake 10,000 minor units.
6. Added append-only `quantlab_goal_decisions`. Both PICK and PASS outcomes are recorded
   with model, policy, quote-pair and arithmetic provenance.
7. Missing model coverage, missing complete quotes, stale quotes, odds limits and
   edge/EV failures are explicit PASS reasons. No model probability is fabricated.
8. When multiple books qualify for the same market/selection/evidence cycle, only the
   best odds become PICK; inferior qualifying books are PASS/BETTER_PRICE_AVAILABLE.
9. A unique first-PICK guard prevents repeated shadow bets for the same
   fixture/market/selection/line/policy. Shadow rows are created only after the PICK
   decision itself is newly persisted.
10. Runtime evaluates persisted GoalLab evidence independently of collection. Therefore
    the daily API ceiling may stop new provider calls while the shadow engine still
    produces decisions from already-stored quotes.
11. GoalLab dashboard now shows an upcoming fixture/decision pipeline with Goal scope,
    Card/Corner scope, last odds capture, latest decision/reason, model and candidate
    edge/EV.

### Data sources / API impact

Task 002 adds **zero provider requests**.

Inputs are:

- persisted `quantlab_fixture_observations`;
- persisted `quantlab_market_observations`;
- read-only active `dixon_coles_model_versions` /
  `dixon_coles_active_models` through the existing validated loader.

The existing collection budget, 1,000/day QuantLab hard ceiling and production reserve
remain unchanged.

### Leakage / provenance

- Decision time must precede kickoff.
- Only market rows with `captured_at <= decision_at` are eligible.
- Complete quote pairs must share fixture, bookmaker, provider bet and capture timestamp.
- Exact immutable `model_version_id` and policy version are persisted with each decision.
- No result, closing price or post-kickoff fact is used to create a PICK.

### Production impact

**NONE.**

No write was added to production `quote_series`, `value_evaluations`,
`pick_decisions`, `registered_picks`, bankroll or active-model state. Production
registration/staking/model behavior is unchanged.

### Verification

Unit, integration, full CI and Railway verification are recorded after the implementation
branch is validated and deployed.


## 2026-09-26 — Task 002 CI verification

**Owner:** QuantLab core + GoalLab

GitHub Actions run `36223824735` passed:

- lint: **PASS**
- full pytest suite: **1009 passed in 26.58s**
- migration chain includes `028_quantlab_goal_shadow_engine.sql`

Isolation diff from Task 002 baseline `c0f3f897a8807f18dd05196335fd53119418be57`
contains QuantLab runtime/docs/migration/tests plus only the two integration assertions
that identify the latest migration. No production model, registration, pick, staking or
bankroll implementation file is changed.

Railway verification follows after merge to main.


## 2026-09-26 — Task 002 Railway verification

**Owner:** QuantLab core + GoalLab

Task 002 merged to main as `fdb2bfede455b34a47cc788ad67b38a1b0d2042e`.

Railway production verification:

- `quantbet-research` deployment `32c2cb15-8af0-4262-929d-104331095063` reached
  **SUCCESS** and its pre-deploy migration step reported `applied 1 migration(s)`,
  applying migration 028 to the shared PostgreSQL database.
- `quantbet-quantlab` deployment `aafdd074-162e-4d24-a1b9-64e128027c5e` reached
  **SUCCESS**. Its migration step reported `applied 0 migration(s)` because migration
  028 had already been applied by the preceding shared-database migration step.
- QuantLab runtime then logged the expected daily API hard-ceiling stop and still ran
  the independent GoalLab evaluator:
  `goal_decisions=0 goal_picks=0`.
- Because `quantlab_goal_decisions` was new and empty at activation, the first-cycle
  zero indicates there were no GOAL_SCOPE_V1 upcoming fixtures available to the
  evaluator from the currently persisted QuantLab fixture universe. The evaluator itself
  started successfully and did not bypass the 1,000/day API ceiling.

Production impact remains **NONE**.


## 2026-09-26 — Task 002 operational bootstrap: current fixture observations

**Owner:** QuantLab core

### Trigger

The first deployed Task 002 runtime was healthy and the shadow engine executed after the
daily API ceiling, but logged `goal_decisions=0 goal_picks=0`.

The reason was structural: migration 026 seeded QuantLab fixture identities from existing
production fixtures but intentionally did not copy fixture observations. Because the
independent global date-shard collector was already blocked by today's exhausted 1,000-call
QuantLab budget, `quantlab_fixture_observations` did not yet contain upcoming rows for the
shadow engine to evaluate.

### Correction

Migration `029_quantlab_fixture_bootstrap.sql` performs a one-time, bounded seed of the
latest already-persisted production fixture observation for current fixtures that have no
QuantLab observation.

- window: one day back through three days forward at migration time;
- no API-Football request is made;
- production tables are read only;
- QuantLab writes only its own fixture identity/observation tables;
- bootstrap rows are explicitly tagged `production-fixture-bootstrap`;
- existing QuantLab observations are never overwritten or supplemented by the bootstrap;
- ongoing fixture discovery remains the independent global date-shard pipeline.

### API-cost impact

**0 provider requests.**

### Production impact

**NONE.** Production fixture rows are read as immutable seed facts only; no production
fixture, model, pick, registration or bankroll state is changed.
