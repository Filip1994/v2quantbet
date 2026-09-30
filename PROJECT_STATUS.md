# QuantBet — Current Project Status

_Last synchronized: 2026-09-30_

This is the canonical current-state snapshot. Historical audits, dated incident reports, Task files and work logs remain valuable evidence but must not override this document when describing the present system.

## 1. Production

Production is live on Railway and uses PostgreSQL as the canonical durable store.

Implemented and wired:

- API-Football fixture discovery with canonical provider identity;
- immutable quote/history ingestion;
- production Dixon-Coles model lifecycle and active model artifacts;
- fixture-bound prediction;
- proportional two-way de-vig;
- value evaluation with persisted raw/model/market probabilities, edge and EV;
- eligibility, freshness, bookmaker, timing and risk boundaries;
- mandatory final quote verification;
- durable pick registration;
- open-exposure accounting;
- Daily Bulletin snapshots;
- registered-pick monitoring and closing;
- result acquisition;
- settlement, bankroll ledger and realized CLV;
- operator PLAYED/SKIPPED event history and effective exposure handling;
- production dashboard/API surfaces.

The engine remains fail-closed for missing model coverage, invalid/stale quotes and model-fit failures.

### Current production limitations

- model coverage is still uneven across some competition/season/team scopes;
- some production training scopes fail with insufficient team history;
- occasional Dixon-Coles optimizer failures are isolated and should be surfaced as explicit coverage loss;
- API-Football fixture identity drift still occurs on individual fixtures, but discovery conflicts are quarantined instead of killing the engine;
- profitability is not treated as proven merely because the pipeline is operational.

## 2. Research Universe

Research is operational and read-only.

Canonical semantics:

- one comparable Research candidate per fixture at the common decision stage;
- `PLAYED`, `SKIPPED` and `BLOCKED_EXPOSURE` routes are retained;
- exposure-only candidates are compared at the same research decision checkpoint as Production candidates;
- raw values are retained in addition to bucket labels;
- model/policy/devig fingerprints are retained where available;
- same-book closing/CLV is used where valid;
- Research never writes Production state.

Research analytics now include:

- model-probability, market-fair-probability, EV and odds buckets;
- market/selection, route, bookmaker, league and freshness cohorts;
- model/policy regime splits;
- lifetime, 30-day, 7-day and weekly stability views;
- N, W/L/V, win rate, expected win rate, calibration gap, flat P&L/ROI;
- CLV coverage, average/median CLV and positive-CLV rate;
- Wilson 95% win-rate intervals;
- drilldowns from cohorts to their exact picks.

## 3. QuantLab

QuantLab is an isolated research runtime with its own state and no Production write path.

### GoalLab

Current family:

- model: **DC+ Pro Structural**
- prefix: `DC_PLUS_PRO_STRUCTURAL_V3:`
- compact structural feature contract: V2
- chronological holdout validation
- leakage audit
- exact immutable model-hash approval boundary

The old 669-active-column / 792-example problem is historical V1 evidence, not the current fitting contract. V2 removed the feature explosion through a compact predeclared core, observation thresholds, regularization and train-fold preprocessing.

### CornerLab

Current family:

- **Corner pressure Poisson GLM**
- structural pre-match team/pressure features
- chronological feature generation
- no bookmaker prices as model inputs
- full-match half-line total-corner market support

The main current bottleneck is historical/team-stat coverage, not a lack of raw training examples. Historical aligned bookmaker calibration remains a priority.

### CardLab

Current family:

- `CARDLAB_REFEREE_POISSON_V1`
- 1xBet Cards Over/Under research path
- referee-history probability source

The current bottleneck is referee-history/data coverage. CardLab should be treated as a data-acquisition/research program before broad model expansion.

## 4. QuantLab analytics UX

GoalLab and CornerLab expose a highlighted **Watchlist · ROI discovery** block before the broader analytics tables.

GoalLab watchlist families include:

- Goal shape × price
- Balance × total-line gap
- Model vs market × price
- Trend × matchup
- Reliability × market

CornerLab watchlist families include:

- Model-line gap × price
- Pressure trend × matchup
- Model vs market × price
- Reliability × market

Bucket labels drill down to the exact settled picks behind the cohort. Table headers are sortable.

## 5. Governance

### Bucket promotion

A bucket does **not** enter Production automatically from analytics.

The explicit owner decision is the Production authority for a bucket-selection rule. Forward/OOS confirmation is useful supporting evidence, but it is not a mandatory gate when the owner deliberately approves the rule.

### Bucket banning

Permanent bans should be conservative. Default policy is to observe a suspected weak bucket for **3–6 months** before permanently banning it.

Immediate suspension is allowed for technical-integrity problems such as:

- leakage;
- wrong settlement semantics;
- fixture/team/bookmaker identity corruption;
- broken quote alignment;
- model/data bug;
- invalid historical reconstruction.

Short-term negative ROI alone is not a technical-integrity failure.

## 6. Release health

At this synchronization point, audited `main` SHA `0733299` had GitHub CI failures in Ruff before pytest ran. The known findings were:

- `RUF007` in `src/h2h/quantlab/dashboard_views.py`;
- `RUF046` in the same module.

Production deployment should be gated on a CI-passing SHA. Railway deployment success and GitHub CI success are separate facts.

See [docs/CURRENT_PRIORITIES.md](./docs/CURRENT_PRIORITIES.md).
