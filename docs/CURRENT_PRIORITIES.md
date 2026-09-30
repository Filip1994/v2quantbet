# QuantBet Football Universe — Current Priorities

_Last synchronized: 2026-09-30_

This is the canonical active-priority and governance document for the football universe.

## Operating rule

The next phase is **release discipline + research governance + data/model coverage**.

It is **not** an architecture rewrite and it is **not** a request for more feature proliferation for its own sake.

## Owner governance

### Production promotion of a bucket

A newly discovered Research/QuantLab bucket may influence Production only through an explicit owner decision.

Rules:

1. analytics and Watchlist views have no automatic Production authority;
2. the owner may approve a bucket for Production when personally convinced by the evidence and football/model logic;
3. forward/OOS confirmation is strongly informative, but it is **not a mandatory gate** for owner approval;
4. the exact approved rule must be versioned/configured explicitly so the decision is auditable;
5. all non-selected candidates should remain observable in Research where the data contract permits it.

### Permanent bucket ban

Permanent removal is intentionally slower than promotion.

Default policy:

- do not permanently ban a bucket because of a short bad run;
- use a **3–6 month observation horizon** before a permanent performance-based ban;
- review N, ROI, CLV, calibration, odds mix, league breadth and regime stability together.

Exception: suspend immediately when there is evidence of a technical-integrity problem such as leakage, bad settlement, invalid identity mapping, corrupted quotes, model bug or unreconstructable decision context.

## P0 — do now

### 1. Restore green CI

Audited `main` SHA `0733299` fails at Ruff before pytest.

Known findings at the sync point:

- `RUF007` — prefer `itertools.pairwise()`;
- `RUF046` — redundant `int()` cast.

After fixing lint, run the full test suite. Green Railway deployment is not a substitute for green CI.

### 2. Gate Production deployment on a validated SHA

Target rule:

```text
commit
→ CI PASS
→ deploy exact validated SHA
→ runtime exposes deployed SHA
```

The runtime/dashboard should expose:

- deployed SHA;
- deployed-at timestamp;
- CI status for that SHA where practical.

### 3. Keep analytics non-authoritative by default

Watchlist/bucket discovery remains aggressive and exploratory, but no dashboard computation should silently rewrite Production policy.

Explicit owner approval remains the promotion boundary.

## P1 — model and data quality

### GoalLab

- separate DC+ validation against league-specific control from validation against pooled fallback control;
- report macro-by-league metrics in addition to global pooled metrics;
- retain exact-hash manual authority;
- continue leakage-safe chronological validation;
- avoid reintroducing V1-style high-dimensional feature expansion.

### CornerLab

- improve historical team/statistics coverage;
- measure coverage drop-off from discovered fixture to modelable fixture;
- build historical bookmaker-aligned calibration/evaluation where data permits;
- track Poisson dispersion and keep Negative Binomial as a measured model alternative rather than an assumption;
- do not lower quality gates merely to manufacture more picks.

### CardLab

- prioritize referee identity/history and canonical card outcomes;
- add league/team discipline context only when timestamp-safe;
- evaluate shrinkage/hierarchical referee rates before trusting small referee samples;
- keep ambiguous card-market semantics excluded until settlement is canonical.

## P1 — analytics and observability

Add/strengthen:

- fixture funnel:
  `discovered → modelable → quote eligible → value evaluated → registered/shadow pick`;
- dropout reasons by league/model/bookmaker;
- model-fit failure counts and examples;
- fixture identity conflict metrics by provider/league/field;
- ROI uncertainty intervals, preferably fixture-level bootstrap for heterogeneous odds returns;
- N, CLV and calibration prominence beside ROI;
- 30/60/90-day stability and league/bookmaker breadth on important buckets.

These are evidence improvements, not mandatory owner-approval gates.

## P1 — codebase maintainability

Gradually split the largest god-modules instead of rewriting the system:

- `src/h2h/quantlab/repository.py`;
- `src/h2h/api/research_dashboard.py`;
- `src/h2h/quantlab/goal_lab/model.py`;
- `src/h2h/quantlab/dashboard_views.py`;
- `src/h2h/quantlab/dashboard.py`;
- `src/h2h/quantlab/runtime.py`;
- `src/h2h/api/dashboard.py`;
- `src/h2h/workers/opportunity.py`.

Introduce typed boundary models for model inputs, analytics rows, quote snapshots and settlement evidence. Prefer incremental typing around interfaces over a broad rewrite.

## P2 — hygiene

- suppress/downgrade benign `BrokenPipeError` / connection-reset logging at the HTTP response boundary;
- require unique monotonic migration prefixes going forward without renaming already-applied migrations;
- remove or clearly mark one-shot Railway diagnostic services;
- add gradual type-checking for critical/new modules;
- consider coverage/dependency-security gates after CI is stable;
- maintain a formal GitHub P0/P1/P2 backlog rather than relying only on work logs.

## Explicit non-priorities

Do **not**:

- rewrite the football universe;
- ban buckets from a short ROI drawdown;
- require an arbitrary forward/OOS waiting period before every owner-approved Production rule;
- treat Railway SUCCESS as proof of CI correctness;
- expand CardLab model complexity before the data foundation improves;
- reintroduce uncontrolled GoalLab feature dimensionality.

## Decision-state vocabulary

For human governance, use:

```text
RESEARCH
→ WATCHLIST
→ OWNER_APPROVED
→ PRODUCTION
→ UNDER_REVIEW
→ BANNED
```

`UNDER_REVIEW` does not imply an automatic ban. `BANNED` is an explicit owner decision.
