# QuantBet fatal production incidents — 2026-09-24

## Scope

This document records two production defects that jointly explained the long no-pick window and the later all-worker outage on 24 Sep 2026.

The fixes are intentionally handled one at a time:

1. **FATAL-01 — fixture discovery identity conflict terminates the entire engine**
2. **FATAL-02 — SKIPPED picks continue reserving registration risk exposure**

The fixture identity invariant itself must remain strict. A provider identity conflict must never be silently accepted or rewritten.

---

## FATAL-01 — discovery identity conflict kills all workers

### Severity

**FATAL / production outage**

### Production symptoms

Railway showed `quantbet-engine` as `CRASHED` while dashboard and Postgres remained available. The dashboard then showed all engine workers as stale because discovery, opportunity, monitoring, model lifecycle, closing proxy, bulletin and results share the same single-leader scheduler process.

The first confirmed fatal recurrence in the inspected production sequence occurred around:

- **2026-09-24 14:07:53 UTC**

The same failure then recurred after restarts, with the final inspected crash at:

- **2026-09-24 14:52:10 UTC**

Exception:

```text
FixturePersistenceConflictError: immutable fixture identity conflicts
```

Call path:

```text
ProductionOrchestrator.run_forever
  -> discovery_cycle
  -> DurableFixtureDiscovery.discover
  -> PostgreSQLFixtureRepository.record_discovery
  -> FixturePersistenceConflictError
```

### Root cause

`DurableFixtureDiscovery` processed the head of its in-memory queue like this:

```python
record_discovery(self._pending[0])
self._pending.popleft()
```

If `record_discovery()` raised an immutable identity conflict:

1. the conflicting item was not removed from the queue;
2. `FixturePersistenceConflictError` was classified by the orchestrator as a fatal invariant error;
3. the exception escaped the discovery job;
4. the whole engine process terminated;
5. after restart, discovery rebuilt work and eventually hit the same conflicting fixture again.

A single poisoned provider fixture could therefore take down every worker in the engine.

### Required behavior

- Keep immutable fixture identity **fail-closed**.
- Never rewrite stored identity to make the provider payload fit.
- Isolate only the conflicting discovery item.
- Log enough stored and incoming identity context to diagnose the mismatch.
- Continue processing later fixtures in bounded units.
- Do not let one provider-data conflict terminate the scheduler.

### Fix status

**FIXED AND PRODUCTION-VERIFIED.**

The patch:

- catches only `FixturePersistenceConflictError` at the durable discovery boundary;
- consumes/quarantines that one in-memory item;
- keeps per-call work bounded by attempted items, including conflicts;
- continues later discovery items;
- preserves repository-level strict rejection;
- logs stored and incoming immutable anchors plus the differing fields.

A regression test proves that a conflicting fixture is skipped while subsequent fixtures in the same bounded batch continue.

### Production verification

- merged commit: `7c34370b404db3b0ddfe6f8132c7f47760429663`;
- Railway deployment: `24bfa70d-7048-41c9-ab16-537389cd5ebf` — `SUCCESS`;
- at **2026-09-24 15:57:34 UTC**, the new diagnostics identified fixture
  `api-football:1601449`;
- stored immutable team anchor: home `2057`, away `814`;
- incoming provider anchor: home `814`, away `2057`;
- conflicting fields: `provider_home_team_id`, `provider_away_team_id`;
- the provider payload therefore represented a home/away swap relative to the stored anchor;
- the conflicting item was quarantined;
- that discovery slice still persisted **9** other fixtures and completed successfully;
- subsequent model lifecycle, opportunity, bulletin, closing and later discovery cycles continued;
- no `QuantBet worker stopped` event followed the conflict.

This confirms that the immutable identity invariant remains enforced while the provider-side conflict can no longer terminate the engine.

---

## FATAL-02 — SKIPPED picks keep the registration risk cap full

### Severity

**FATAL to pick production / no-registration lockout**

This defect did not crash the process, but it could suppress every otherwise-valid new pick.

### Production symptoms

The last confirmed registered pick in the inspected window was:

- **2026-09-24 05:03:54 UTC** (`registered_picks=1`)

Later production diagnostics repeatedly showed:

```text
open_exposure_minor = 300000
max_open_exposure_minor = 300000
fixed_stake_minor = 30000

risk_reserved_pick_count = 10
risk_reserved_played_count = 5
risk_reserved_skipped_count = 5
risk_reserved_played_minor = 150000
risk_reserved_skipped_minor = 150000
```

At the same time, valid value candidates reached the registration layer and were rejected only by:

```text
MAX_OPEN_EXPOSURE_EXCEEDED
```

Representative example from fixture `api-football:1568188`:

- OU 2.5 UNDER @ 2.05
- edge about +28.00 percentage points
- EV about +51.81%
- rejection: `MAX_OPEN_EXPOSURE_EXCEEDED`

Additional candidates on the same fixture also passed value thresholds and were blocked by the same exposure gate.

### Root cause

Registration exposure currently counts unresolved `STAKE_RESERVED` ledger entries until terminal settlement.

The exposure query does not exclude a pick whose latest operator state is `SKIPPED`.

Therefore a pick that the operator explicitly did not place can still reserve risk capital for registration.

Observed production composition:

- 5 PLAYED reservations = 1,500 RSD
- 5 SKIPPED reservations = 1,500 RSD
- registration exposure = 3,000 RSD
- configured cap = 3,000 RSD

The five SKIPPED picks therefore occupied half of the registration cap even though no stake was actually placed.

### Required behavior

The registration risk gate must use exposure that reflects real operator stake commitment.

At minimum:

- latest operator state `SKIPPED` must not consume open registration exposure;
- `PLAYED` and default/no-override picks retain current reservation behavior unless deliberately changed;
- terminal settlement semantics remain authoritative for played bets;
- duplicate-fixture protection remains independent;
- ledger history remains append-only and auditable.

### Fix status

**FIXED AND PRODUCTION-VERIFIED.**

The patch changes the registration exposure gate so unresolved reservations consume
`MAX_OPEN_EXPOSURE` only when the latest operator state is `PLAYED` (or no override exists,
which preserves the default PLAYED behavior).

A `SKIPPED` reservation remains present in immutable system history and remains visible in
the diagnostic counts/amounts, but contributes zero to effective registration exposure.

The dashboard `Risk exposure / cap` value is aligned to the same PLAYED-only operator
exposure so the UI does not report a full risk cap when registration has capacity.

System settlement/model history and the append-only system ledger are intentionally not
rewritten by this fix.

### Verification

Code/CI:
- PR #62 was squash-merged as `f53afebbbc0a0c8902a28e00bdc3641d5c0a397e`;
- lint passed;
- the new PostgreSQL regression test passed: a first pick fills a one-stake exposure cap,
  becomes `SKIPPED`, effective exposure becomes zero, and a second otherwise-eligible pick
  can register successfully;
- the immutable ledger retains both `STAKE_RESERVED` facts in that regression test;
- the full suite still reported the same eight pre-existing baseline failures seen before
  this patch; FATAL-02 introduced no new test failure.

Production:
- Railway engine deployment `4660b739-144a-4316-8180-12b4a5fe0a2e` reached `SUCCESS`;
- Railway dashboard deployment `061afb29-954f-4805-be4d-7ed9d2b1d8cd` reached `SUCCESS`;
- service configuration, bankroll parameters, fixed stake and max exposure settings were
  preserved during the exact-commit engine deployment;
- the first authoritative engine snapshot after rollout reported:
  - `open_exposure_minor = 150000`;
  - `risk_reserved_pick_count = 10`;
  - `risk_reserved_played_count = 5`;
  - `risk_reserved_played_minor = 150000`;
  - `risk_reserved_skipped_count = 5`;
  - `risk_reserved_skipped_minor = 150000`;
- before the fix the same 10-reservation composition produced
  `open_exposure_minor = 300000`.

Therefore the five SKIPPED reservations remain fully auditable but no longer consume
registration capacity. Effective exposure dropped from **3,000 RSD to 1,500 RSD** without
raising the configured **3,000 RSD** cap or changing the **300 RSD** fixed stake.

The first post-rollout opportunity slice had all eight eligible fixtures waiting for their
normal refresh cadence, so it did not provide a fresh live candidate-registration example.
The PostgreSQL regression test proves both preliminary and final registration behavior, and
the production risk snapshot proves the corrected exposure semantics are active on the live
dataset.

### Residual FATAL-02 race found and closed

The first FATAL-02 patch correctly released SKIPPED exposure for registration, but a second
failure mode was found during closure audit:

1. pick A is SKIPPED and frees one stake unit;
2. pick B registers into the newly free capacity;
3. pick A is later changed back to PLAYED;
4. without a shared lock and cap check, effective exposure could exceed
   `max_open_exposure_minor`.

This hard-risk invariant is now closed.

Final hardening:
- PR #64 squash commit: `363ae02143b5f30e69f0756e54ff38beccb29661`;
- registration and unresolved `SKIPPED -> PLAYED` reactivation serialize on the same
  bankroll row lock;
- both use the same effective PLAYED unresolved-exposure calculation;
- if released capacity has already been consumed, reactivation is rejected instead of
  allowing exposure above the configured cap;
- settled/history-only PLAYED restores remain allowed because they create no open exposure;
- no ledger history is rewritten.

CI verification:
- lint: PASS;
- full suite: **950 passed, 8 failed**;
- the eight failures are the same known baseline failures that existed before this patch;
- both new FATAL-02 hard-risk tests passed:
  - capacity-consumed reactivation is blocked;
  - concurrent registration/reactivation at a one-stake cap permits only one exposure winner.

Production verification:
- Railway engine deployment `326b0420-8f92-4b82-808c-b0e5b62e5f32`: **SUCCESS**;
- no bankroll, fixed-stake, max-exposure, model or provider configuration changed;
- production leadership acquired normally;
- all scheduler workers resumed successfully;
- no `QuantBet worker stopped` event was observed after rollout;
- startup effective exposure was **1,800 RSD** from 6 PLAYED reservations, while the
  5 SKIPPED reservations (1,500 RSD) remained auditable but excluded from hard exposure;
- configured hard cap remained **3,000 RSD**.

Live proof that the original FATAL-02 registration lockout is resolved occurred immediately
before the hardening rollout: at **2026-09-24 16:13:51 UTC**, fixture
`api-football:1583771` reached mandatory final quote verification and one new pick was
registered. The next production startup therefore showed 11 unresolved reservations split
6 PLAYED / 5 SKIPPED, with effective exposure only 1,800 RSD.

FATAL-02 is now considered **closed**.

---

## Production repair order

1. Patch, test and deploy FATAL-01.
2. Verify engine remains alive through the formerly recurring discovery-conflict window and capture the exact conflicting fixture identity from new structured logs.
3. Only then patch FATAL-02.
4. Verify risk exposure drops by the SKIPPED reservation amount without changing the configured cap.
5. Confirm that an otherwise-qualified new candidate can progress beyond the preliminary risk gate when capacity is available.

---

## Non-goals

These incidents must not be used as justification to:

- weaken model probability, edge or EV thresholds;
- increase `MAX_OPEN_EXPOSURE`;
- alter the fixed stake;
- accept conflicting immutable fixture identities;
- fabricate fresh odds;
- rewrite historical ledger or quote facts.
