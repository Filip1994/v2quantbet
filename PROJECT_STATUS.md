# Project Status

## Current task
C5 — odds domain and canonical quote pipeline

## Completed
- A1 — repository skeleton.
- A2 — development tooling and minimal test setup.
- A3.1 — standard local quality checker used by CI.
- A3.2 — local Python version pinned to 3.11.
- A3.3 — dependency lockfile (`uv.lock`) created and committed.
- A3.4 — CI verified with the locked dependency environment.
- A4.1 — minimal configuration contract implemented and tested.
- A4.2 — configuration representation redacts database/API secrets and is tested.
- B1 — Railway PostgreSQL production infrastructure verified.
- B2 — legacy PostgreSQL application tables identified and removed; empty state verified.
- B3.1 — PostgreSQL read readiness verified with `SELECT 1`.
- B3.2 — database identity verified (`railway` / `postgres`).
- B3.3 — no application tables remain in `public`.
- B3.4 — Railway PostgreSQL service, replica, and persistent volume verified.
- C1 baseline — legacy quant reference commit and regression anchors recorded in `docs/quant-golden-master.md`.
- C2 — deterministic executable golden-master fixture and Dixon–Coles regression tests added.
- C3 — quant boundary, edge-case, numerical-stability, market-invariant, and determinism tests added; CI verified green at 2026-09-12T21:45:47Z in run 64 (`8cbe89807f5d61087089b7391c28ebc2e3630f0f`).
- Quant namespace consolidation — canonical `h2h` namespace selected and duplicate domain namespace removed.
- C4.1 — public quant API exports verified; CI verified green in run 69 (`5b0314abe24a67a009087d786ecf5a3133fb3b0c`).
- C4.2 — public quant API behavior contract documented and tested, including inputs, outputs, error boundaries, numerical invariants, determinism, and golden-master compatibility; CI verified green at 2026-09-12T22:45:58Z in run 72 (`ea4d1f28215a7988312d2d4d8712d008bb`).
- C5.1 — canonical market snapshots cover OU_25 and BTTS two-sided invariants; CI verified green in run 77 (`85007ecdee2aea1f08cd854603fe5aeef8c3e553`).
- C5.2 — canonical quotes reject non-finite odds (`NaN`, positive infinity, and negative infinity); CI verified green in run 78 (`e4bcbbf3181020743423969ea7affc84bbc3be69`).
- C5.3 — canonical quotes reject blank required text fields; CI verified green at 2026-09-12T23:01:02Z in run 82 (`aba96ea0daf09d9bb7951c93268f610010b8d127`).
- No API keys or secrets included.

## Next
C5 — odds domain and canonical quote pipeline

## Non-negotiable rules
1. One small task at a time.
2. Tests before moving to the next task.
3. Quant mathematics is frozen until golden-master tests exist.
4. Do not introduce odds-provider-specific structures into the quant layer.
5. Do not put secrets in Git.
6. No claim of completion without a verified test result.
