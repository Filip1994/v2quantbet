# QuantBet — Historical Pre-Match Quotes Design

**Status:** Design proposal — not implemented  
**Design timestamp:** `2026-09-14T00:00:00Z`  
**Scope:** Pre-match odds only; live/in-play odds are explicitly excluded.

## 1. Problem

The current quote persistence model treats `(fixture_id, bookmaker_id, market, selection)` as a unique identity. That is insufficient for QuantBet because the same market selection must be observed repeatedly over time.

QuantBet must preserve the evidence required to show:

- the first valid quote observed;
- the quote used when a pick was registered;
- the latest valid pre-match quote;
- the last valid pre-kickoff quote used as the closing reference;
- the complete sequence of valid pre-match observations;
- the exact snapshot referenced by a pick and by CLV calculations.

## 2. Design principles

1. **Append-only observations:** a historical snapshot is never overwritten.
2. **Stable quote-series identity:** the market/selection identity identifies a series, not one observation.
3. **Immutable pick reference:** a registered pick points to one exact quote snapshot.
4. **Explicit lifecycle:** snapshots are valid only within the pre-match lifecycle.
5. **Deterministic closing rule:** closing means the latest valid snapshot observed before the actual kickoff time, subject to freshness and validity rules.
6. **Provider-neutral domain boundary:** provider payloads do not enter persistence or quant logic.
7. **Restart safety:** repeated ingestion of the same observation must be idempotent.
8. **No live scope:** observations after kickoff are rejected or excluded from this model.

## 3. Logical model

### 3.1 Quote series

A `QuoteSeries` identifies one fixture, bookmaker, market and selection:

- `series_id` — stable internal identifier;
- `fixture_id`;
- `bookmaker_id`;
- `market`;
- `selection`;
- `created_at`.

The series is not itself a price observation.

### 3.2 Quote snapshot

A `QuoteSnapshot` is one immutable observation in a series:

- `snapshot_id` — stable unique identifier;
- `series_id`;
- `odd`;
- `observed_at` — provider observation time, timezone-aware;
- `captured_at` — time QuantBet persisted the observation, timezone-aware;
- `source`;
- `is_valid` / validation outcome;
- optional provider trace metadata that remains outside the canonical quant contract.

The canonical quote value and observation timestamp are mandatory. `captured_at` is required for operational traceability.

### 3.3 Pick entry reference

`PickRegistration` must reference the exact `snapshot_id` used at registration time. The pick should also retain the denormalized entry odd for immutable decision readability, but the snapshot reference remains authoritative for traceability.

Required relationship:

```text
PickRegistration ──> QuoteSnapshot ──> QuoteSeries
```

A later quote update must never mutate the entry snapshot or the registered pick.

## 4. Derived checkpoints

The following are read models or deterministic queries over immutable snapshots:

- **first_seen:** earliest valid snapshot in the series;
- **entry:** snapshot explicitly referenced by the registered pick;
- **current_pre_match:** latest valid snapshot captured before kickoff;
- **closing_pre_match:** latest valid snapshot whose observation/capture is accepted as pre-kickoff under the closing policy.

Each checkpoint must return the complete snapshot identity and timestamp, not only the odd value.

The entry checkpoint is not inferred from ordering; it is an explicit immutable reference.

## 5. Kickoff and closing policy

1. The fixture must have a trusted kickoff timestamp.
2. The monitor may ingest only snapshots belonging to the pre-match lifecycle.
3. Once kickoff has passed, no new snapshot may become a closing candidate for that fixture.
4. The closing reference is selected deterministically from valid snapshots before kickoff.
5. If no valid pre-kickoff snapshot exists, the closing checkpoint is `unavailable`, not fabricated.
6. A late-arriving observation must not silently rewrite a previously finalized closing result without an explicit correction/audit operation.

The exact tolerance for clock skew, delayed provider timestamps and finalization timing must be defined in a later implementation decision.

## 6. Repository boundary proposal

The current `QuoteRepository` contract should be replaced by a history-aware contract with operations conceptually equivalent to:

- `ensure_series(...)`;
- `append_snapshots(...)`;
- `snapshots_for_series(series_id)`;
- `series_for_fixture(fixture_id)`;
- `first_seen(series_id)`;
- `latest_pre_match(series_id, kickoff_at)`;
- `closing_pre_match(series_id, kickoff_at)`;
- `get_snapshot(snapshot_id)`.

Exact names, return types, transaction semantics and conflict rules require approval before implementation.

## 7. Idempotency and conflicts

A snapshot deduplication key must be defined before coding. The candidate key is based on the stable series identity plus the observation timestamp and canonical quote data. The system must distinguish:

- an exact replay of the same observation — idempotent no-op;
- a different observation at a different time — new history row;
- conflicting data for the same deduplication key — explicit conflict;
- invalid or post-kickoff data — rejected with a reason.

## 8. Monitoring boundary

The background monitor is responsible for:

- selecting active pre-match fixtures and registered picks;
- collecting provider data at a budget-aware cadence;
- normalizing and validating quotes;
- appending valid snapshots;
- recording failures, staleness and rate-limit outcomes;
- stopping fixture monitoring after kickoff;
- allowing the dashboard to read persisted state without requiring the dashboard to be open.

The monitor is not responsible for changing historical snapshots or pick decisions.

## 9. CLV readiness

The persistence model must make it possible to calculate realized CLV from:

- immutable entry snapshot / entry odd;
- deterministic closing snapshot / closing odd;
- explicit CLV methodology version;
- timestamps and source provenance for both snapshots.

No realized CLV should be marked final when the closing reference is unavailable or ambiguous.

## 10. Out of scope

- live/in-play odds;
- automatic betting or order execution;
- PostgreSQL schema migration;
- background worker implementation;
- dashboard implementation;
- final clock-skew and stale-data policy;
- exact repository method names;
- pick persistence implementation.

## 11. Approval gate

This document is a design proposal. Implementation must not begin until the following are explicitly approved:

- history-aware repository contract;
- snapshot deduplication key;
- kickoff/closing policy;
- treatment of late-arriving observations;
- relationship between `PickRegistration` and `QuoteSnapshot`;
- PostgreSQL schema and transaction strategy.
