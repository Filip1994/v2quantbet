# QuantBet — Execution Plan

## 1. Purpose of this document

This document is the canonical execution plan for QuantBet. It summarizes the product goal, the decisions made during planning, the current architectural direction, and the implementation order.

The system is not intended to be only a one-time prediction generator. Its first useful product is a daily bulletin of value picks, followed by continuous pre-kickoff odds monitoring. Later phases add research and intraday strong signals.

## 2. Product goal

QuantBet is a football value-betting research and monitoring system that:

1. scans relevant upcoming fixtures;
2. evaluates bookmaker odds against quantitative model probabilities;
3. publishes a daily bulletin of the strongest currently valid opportunities;
4. continues tracking published picks and market movement until kick-off;
5. preserves the evidence needed to calculate and evaluate CLV;
6. later uses accumulated historical data for controlled research and model improvement;
7. eventually emits strong signals during the day when new information or market movement creates a qualifying opportunity.

The system must prioritize reproducibility, traceability, data quality, and measurable performance over premature infrastructure complexity.

## 3. Three major product phases

# Phase I — Bulletin picks and pre-kickoff monitoring

This is the first production target and must be completed before research or intraday signals are introduced.

### 3.1 Daily bulletin

Every day, shortly after midnight—target approximately 10–15 minutes after 00:00—the system should:

1. identify relevant fixtures in the configured horizon, initially up to 72 hours;
2. collect available fixture and bookmaker odds data;
3. validate and normalize the data;
4. calculate model probability, implied probability, fair odds, edge/value, and quality flags;
5. select and rank the best qualifying opportunities;
6. publish a daily bulletin;
7. register every published pick with immutable decision context.

The bulletin must distinguish between:

- newly published picks;
- currently actionable picks;
- already monitored or expired picks;
- rejected or stale opportunities.

The bulletin is a decision snapshot. It is not the end of the system's work for that day.

### 3.2 Pick registry

Every bulletin pick must preserve, at minimum:

- unique pick identifier;
- fixture identifier;
- market and selection;
- bookmaker;
- pick timestamp;
- odds at pick time;
- model probability;
- implied probability;
- fair odds;
- edge/value calculation;
- model and configuration version;
- applied filters and decision metadata;
- expected-CLV signal and methodology version, if implemented.

Published decision context must be immutable. Later market changes must be stored as new observations, never by overwriting the original pick.

### 3.3 Continuous odds monitoring

After the bulletin is published, the system must continue monitoring relevant fixtures and especially all published picks until kick-off.

The monitoring worker must:

- refresh odds at a configurable cadence;
- preserve every relevant odds snapshot;
- track odds movement from pick time onward;
- record data freshness and source metadata;
- stop monitoring a fixture when its kick-off has passed;
- handle stale, missing, conflicting, or rate-limited data safely;
- respect the provider's API budget.

The initial monitoring cadence may be approximately 30 minutes, but the final cadence must be budget-aware. Refresh frequency should increase near kick-off where justified and should prioritize active picks.

### 3.4 Required odds checkpoints

For each tracked pick, the system must expose and preserve:

- **first seen odds** — earliest valid captured quote;
- **pick odds** — quote used when the pick was published;
- **current odds** — latest valid quote;
- **closing odds** — last valid quote captured before kick-off and accepted as the closing reference.

Each checkpoint must be timestamped and traceable to an underlying snapshot.

### 3.5 CLV boundary

The implementation must keep these concepts separate:

- **value/edge:** model probability versus bookmaker-implied probability at decision time;
- **expected CLV:** optional forecast of future market movement, using a separately versioned methodology;
- **realized CLV:** calculation based on pick-time odds and a valid closing reference.

Realized CLV must not be calculated merely because a quote moved during the day. It requires a defined closing reference and must be preserved with its methodology/version. The final realized-CLV evaluation may be finalized after the event lifecycle provides the required valid reference and settlement context.

### 3.6 Phase I completion criteria

Phase I is complete only when the system can reliably demonstrate:

- daily bulletin generation after midnight;
- valid pick selection and immutable registration;
- continuous refresh until kick-off;
- historical odds snapshots;
- first-seen, pick-time, current, and closing checkpoints;
- reproducible value calculations;
- valid CLV inputs and calculation boundaries;
- restart-safe behavior and no silent history overwrites;
- tests covering the complete bulletin-to-kickoff flow;
- a basic operational view of the system.

# Phase II — Research sector and controlled model improvement

Research begins only after Phase I produces enough trustworthy historical data.

### 4.1 Research objective

The research sector should determine, using evidence, which additional features and decision rules improve pick quality, calibration, realized CLV, or other explicitly selected performance measures.

The model must not be allowed to change itself blindly in production. Research must be versioned, reproducible, and separated from the live decision path.

### 4.2 Candidate research features

Research may evaluate, where reliable data exists:

- market type;
- bookmaker disagreement;
- time remaining until kick-off;
- first-seen odds;
- pick-time odds;
- odds movement before the pick;
- odds movement velocity and direction;
- market liquidity or breadth proxies;
- league and competition;
- home/away context;
- injuries, lineups, and team news;
- weather and pitch conditions;
- model calibration by market and competition;
- data freshness and provider quality;
- historical CLV patterns;
- interactions between model edge and market movement.

These are research hypotheses, not assumed signals. Every feature must be evaluated for data quality, leakage, stability, and out-of-sample performance.

### 4.3 Research workflow

1. Build a historical dataset from immutable snapshots, picks, closing references, and outcomes.
2. Define the target metric and evaluation window.
3. Form a specific hypothesis.
4. Build the feature using only information available at the relevant decision time.
5. Run backtests and out-of-sample evaluation.
6. Compare against the current production baseline.
7. Record results, limitations, and the exact feature/model version.
8. Promote a change only through an explicit release decision.

Research must guard against look-ahead bias, survivorship bias, data leakage, and overfitting.

### 4.4 Phase II completion criteria

Phase II is complete when QuantBet has:

- a reproducible research dataset;
- documented evaluation metrics;
- baseline-versus-experiment comparisons;
- versioned research outputs;
- a controlled promotion process;
- evidence that any promoted improvement is real and not merely backtest noise.

# Phase III — Intraday strong signals

This phase adds a second live output channel after the bulletin and research foundations are reliable.

### 5.1 Strong-signal objective

During the day, QuantBet continuously evaluates the broader upcoming-fixture universe. If a fixture or market that did not qualify for the bulletin later satisfies the configured criteria, the system may emit a strong signal immediately rather than waiting for another batch.

Signals may be emitted one at a time.

### 5.2 Possible trigger conditions

A strong signal may be considered when there is a validated combination of:

- newly available market data;
- improved model edge;
- meaningful odds movement;
- bookmaker disagreement;
- a newly opened market;
- improved data quality;
- a relevant time-to-kickoff window;
- research-approved feature patterns;
- explicit risk and freshness checks.

A market movement alone is not automatically a strong signal. The signal must include an explanation and the complete decision context.

### 5.3 Strong-signal record

Each signal must preserve:

- signal identifier;
- fixture and market/selection;
- emission timestamp;
- odds at signal time;
- model and configuration version;
- value/edge metrics;
- trigger reason;
- data-quality and freshness flags;
- whether the signal was previously in the bulletin;
- monitoring lifecycle through kick-off.

### 5.4 Phase III completion criteria

Phase III is complete when the system can:

- continuously scan the live opportunity universe;
- detect newly qualifying opportunities;
- emit deduplicated signals in near-real time within API constraints;
- explain why each signal was emitted;
- monitor signals through kick-off;
- preserve all evidence for later research and evaluation;
- avoid repeatedly emitting the same unchanged signal.

## 4. Dashboard — operational eyes of the system

The Super Dashboard is a read-only operational view. It should expose the state of the complete lifecycle without becoming a complex interactive application.

It should show:

- system health and last successful refresh;
- API budget usage and rate-limit events;
- upcoming fixtures;
- bulletin picks;
- intraday strong signals, once Phase III exists;
- first-seen, pick-time, current, and closing odds;
- odds movement history;
- value, edge, and model version;
- expected CLV, where available;
- realized CLV when valid;
- stale or missing data;
- rejected opportunities and reasons;
- monitoring status through kick-off;
- research/model version provenance.

The dashboard is not the first implementation target. It becomes useful after the underlying lifecycle and data contracts exist.

## 5. Architecture and infrastructure principles

### 5.1 Keep the first system simple

The initial implementation should remain a modular monolith with clear boundaries:

- fixture discovery;
- odds ingestion;
- normalization and validation;
- quant evaluation;
- pick registry;
- monitoring scheduler;
- CLV calculation;
- bulletin generation;
- research dataset/export;
- dashboard projection.

Do not introduce microservices, Kafka, Kubernetes, Redis, websockets, or a complex frontend before measured need exists.

### 5.2 Railway direction

Railway is a suitable deployment platform for the first continuous worker, provided persistence is handled correctly.

The intended runtime is a long-running monitoring worker, not merely a short daily batch:

```text
Railway monitoring worker
        │
        ├── fixture discovery
        ├── odds refresh loop
        ├── bulletin generation after midnight
        ├── pick monitoring until kick-off
        ├── CLV checkpoint collection
        └── dashboard/bulletin projection
```

A persistent volume may be acceptable for an early single-worker SQLite deployment. PostgreSQL remains the planned canonical production state store when concurrency, reliability, multiple services, or broader research workloads justify it.

### 5.3 API budget is a product constraint

Refresh cadence must be designed around the provider budget. The system should:

- prioritize active picks;
- refresh nearer kick-off more frequently when justified;
- refresh distant fixtures less frequently;
- stop querying after kick-off;
- reserve budget for critical checks;
- record budget consumption and rejected calls.

## 6. Current repository position

The repository already contains substantial foundation work:

- quantitative/domain foundation and regression protection;
- canonical quote and market snapshot models;
- provider-neutral quote adapter contract;
- API-Football normalization, ingestion, deduplication, and conflict handling;
- in-memory and SQLite persistence;
- application composition and configuration;
- provider-neutral HTTP transport;
- retry and rate-limit handling;
- daily API budget protection;
- fixture-level in-memory API response cache;
- tests and documentation for those foundation components.

This work is useful, but it is not yet the product itself. The next work must move toward the first vertical product slice: bulletin generation and monitoring through kick-off.

## 7. Immediate implementation order

The next implementation sequence is:

1. Audit the existing repository against this plan and `QUANTBET_GOALS.md`.
2. Validate actual API response contracts and fixture lifecycle data.
3. Implement the minimum quant value-evaluation service.
4. Implement immutable pick registration.
5. Implement the daily bulletin generator, scheduled shortly after midnight.
6. Implement the monitoring worker and budget-aware refresh scheduling.
7. Persist odds snapshots and required checkpoints through kick-off.
8. Implement the CLV calculation boundary and tests.
9. Add an end-to-end test from fixture/odds ingestion to bulletin and closing checkpoint.
10. Generate a read-only operational dashboard projection.
11. Deploy the continuous worker on Railway with durable persistence.
12. Run a real-data pilot and fix data-quality/operational issues.
13. Only then start the research sector.
14. Only after research validation implement intraday strong signals.

## 8. Explicit non-goals for now

Do not currently prioritize:

- autonomous model self-modification;
- automatic bookmaker betting or order execution;
- complex machine-learning ensembles;
- real-time websockets;
- multi-service deployment;
- distributed caching;
- elaborate observability platforms;
- advanced frontend interactions;
- premature PostgreSQL migration if the selected pilot architecture does not require it.

## 9. Definition of success

The first meaningful success is not a sophisticated dashboard or a complex ML model. It is a trustworthy daily operational loop:

> After midnight, QuantBet publishes a reproducible bulletin of value picks, then refreshes and records market movement for those picks until kick-off, preserving enough evidence to evaluate the decisions and CLV later.

Everything else should be built around making that loop correct, observable, and researchable.
