# Project Status

## Current task
C2 — executable golden-master fixture and regression test

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
- Quant namespace consolidation — canonical `h2h` namespace selected and duplicate domain namespace removed.
- No API keys or secrets included.

## Next
C3 — quant boundary, edge-case, and numerical-stability tests.

## Non-negotiable rules
1. One small task at a time.
2. Tests before moving to the next task.
3. Quant mathematics is frozen until golden-master tests exist.
4. Do not introduce odds-provider-specific structures into the quant layer.
5. Do not put secrets in Git.
6. No claim of completion without a verified test result.
