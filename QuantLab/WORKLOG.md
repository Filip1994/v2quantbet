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
