# Production VOID, Skip and history

When the user asks to void a Production pick, use the Production-only procedure
`production_void_pick(pick_id, request_id, actor, reason)` introduced by migration
072. Resolve each supplied short ID uniquely and verify the fixture names first.
Do not use `manual_void_postponed_pick.py`, CornerLab settlement events, provider
observations or research pick mutations for a Production-only request.

The procedure appends one audited override per Production pick. The same request,
actor and reason can safely be retried; contradictory retries fail. It preserves
the actual PLAYED/SKIPPED/PENDING decision. VOID returns the stake in the computed
Production balance, realizes zero P&L and removes open exposure. It does not write
to the legacy registered-pick bankroll ledger.

With DATABASE_PUBLIC_URL (or DATABASE_URL) configured and PYTHONPATH=src:

```sh
python scripts/manage_production_picks.py void b799cf341e cf5d593354 f802368322 --actor operator --reason "User requested VOID" --request-id production-void-20261029
# Inspect the names, then repeat with --apply to commit all targets atomically.
```

Skip persists an append-only Production state event. Skipped picks are excluded
from both HTML and JSON Production output, immediately after the POST invalidates
the snapshot cache. The immutable clone remains registered, preventing reintake.
Finished picks enter history only if their effective operator decision is PLAYED.
A pending or skipped pick is never relabeled as PLAYED by a manual void.

The authorized one-time history reset uses:

```sh
python scripts/manage_production_picks.py clear-history --actor operator --reason "User requested empty Production history" --request-id production-history-reset-20261029
# Inspect, then repeat with --apply.
```

This archives the currently visible finished PLAYED picks without deleting facts.
They also leave Production performance totals, so those totals start afresh.
Open picks remain active. Reset request IDs are recorded even for an empty history;
retrying a completed request does not archive future picks. Research views, source
results and research analytics are unaffected.

After an operation, verify: target overrides exist once, outcome VOID/P&L 0,
open exposure reflects the remaining open picks, skipped picks are absent, and
every history row is PLAYED. The dashboard and production intake engine both need
the void-aware exposure projection; deploy migration 072 before that code.
