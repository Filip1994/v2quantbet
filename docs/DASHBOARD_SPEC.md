# QuantBet — Dashboard Specification

## 1. Product decision

QuantBet does **not** need an interactive frontend dashboard.

The dashboard is a **read-only, server-rendered operational page**. Its purpose is to make the complete pick history and bankroll state visible in one place. It must not be responsible for discovery, odds collection, model calculation, settlement, or monitoring.

The dashboard reads persisted PostgreSQL state produced by the engine and renders an HTML page. No WebSocket layer, React application, client-side state management, or dashboard-side write operations are required for V1.

## 2. Core objectives

The page must show:

- current bankroll state;
- all registered picks in reverse chronological order;
- active, won, lost, void, expired, and rejected pick statuses where applicable;
- the complete odds lifecycle for every pick;
- stake, profit/loss, and resulting bankroll movement;
- enough provenance to audit why and when a pick was created.

The page is a reporting surface, not a trading interface.

## 3. Bankroll model

Initial bankroll:

```text
30,000 RSD
```

The bankroll must be represented through an append-only ledger rather than a single mutable balance field.

Each ledger entry should contain at least:

- ledger entry ID;
- timestamp;
- related pick ID, when applicable;
- entry type;
- amount in RSD;
- balance after entry;
- explanatory metadata.

Minimum entry types:

- `INITIAL_BANKROLL`;
- `STAKE_RESERVED` or `STAKE_PLACED`;
- `PAYOUT`;
- `LOSS`;
- `VOID_REFUND`;
- `MANUAL_ADJUSTMENT` only through an explicitly controlled administrative path.

The displayed balance must be reproducible from the ledger. A mutable balance cache may be added later for performance, but it cannot be the source of truth.

## 4. Stake policy

The initial stake policy must be explicit and versioned. The dashboard should display the applied stake for each pick, but it must not calculate or alter stakes itself.

Until a separate risk-policy decision is implemented, the system should support a configurable fixed-stake policy and preserve:

- stake amount;
- stake-policy name/version;
- bankroll reference at decision time;
- risk flags;
- whether the pick was actually counted in bankroll accounting.

No pick should silently affect the bankroll merely because it was displayed on the page.

## 5. Odds checkpoints per pick

Every registered pick should expose these distinct values:

1. **First seen odds** — earliest valid quote captured for the relevant fixture/market/selection.
2. **Pick odds** — exact quote used in the decision and bulletin publication.
3. **Current odds** — latest valid quote available before kick-off or at the last refresh.
4. **Closing odds** — final accepted pre-kickoff quote used as the closing reference.

For each checkpoint preserve:

- decimal odds;
- timestamp;
- bookmaker/source;
- underlying snapshot ID;
- data-quality/freshness status.

The system must never overwrite the original first-seen or pick-time values when later quotes arrive.

## 6. Pick history table

The main page should display every pick, newest first, with at least:

- pick ID;
- kickoff time;
- fixture;
- league/competition;
- market and selection;
- pick status;
- first seen odds;
- pick odds;
- current odds;
- closing odds;
- model probability;
- implied probability;
- edge/value;
- stake in RSD;
- realized profit/loss in RSD;
- CLV status/value when valid;
- model/configuration version;
- data-quality warning, if any.

Rows may link to a non-interactive detail page for the full audit record, but no mutation controls are needed.

## 7. Summary section

At the top of the page display:

- initial bankroll: `30,000 RSD`;
- current bankroll;
- total staked;
- settled stakes;
- gross returns;
- realized profit/loss;
- number of picks;
- active picks;
- won/lost/void counts;
- pending settlement amount;
- last engine refresh;
- last dashboard generation time.

All monetary values must be displayed in RSD with consistent rounding rules.

## 8. Operational status

A compact status block should show:

- engine heartbeat/last successful cycle;
- last discovery timestamp;
- last odds ingestion timestamp;
- number of recent ingestion failures;
- stale-data warning;
- database connectivity status;
- provider rate-limit status, when available.

This is informational only.

## 9. Architecture

```text
QuantBet engine/worker
        │
        ▼
PostgreSQL source of truth
        │
        ▼
Read-only dashboard query/projection layer
        │
        ▼
Server-rendered HTML page
```

The dashboard must not:

- call API-Football directly;
- write odds or pick records;
- settle picks;
- change bankroll values;
- trigger worker jobs;
- require the page to remain open for monitoring.

## 10. Implementation order

1. Define and test pick lifecycle records.
2. Define and test bankroll ledger and settlement accounting.
3. Persist immutable odds checkpoints and closing references.
4. Create read-only dashboard query models.
5. Implement a minimal server-rendered HTML page.
6. Add a complete historical pick table.
7. Add summary bankroll metrics and operational status.
8. Add a non-interactive pick detail view if needed.
9. Deploy as a separate read-only Railway service or route, without coupling it to the worker loop.

## 11. V1 scope boundary

Dashboard V1 intentionally excludes:

- interactive filters and controls;
- editing picks;
- manual settlement from the browser;
- placing bets;
- real-time push updates;
- complex charts;
- user accounts and multi-user permissions beyond the minimum deployment protection.

A simple page refresh is sufficient for V1.
