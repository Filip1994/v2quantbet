# Production result conflict: bounded isolation

**Status: CODE READY for isolation; incident root cause UNKNOWN.** This branch does not change a result, provider record, settlement formula, bankroll, betting decision, or production configuration. No deployment has occurred.

## Evidence and scope

`ReconcileFixtureResults.execute()` previously called `persist_result()` outside an item-level error boundary. `ResultPersistenceConflictError` belongs to the orchestrator's fatal invariant set, so one disputed fixture stopped the entire production engine. The exact production conflict source has not been established: the durable fixture identity, acquired provider payload, and matching timestamps must be compared read-only before claiming a root cause. Do not infer which side is wrong from the exception class.

The change catches **only** `ResultPersistenceConflictError` around `persist_result()`, calls the existing `results` item-failure recorder, and moves to the next claimed fixture. The repository's transaction context rolls back the disputed observation on exception. That fixture never reaches `stable_result()`, pick settlement or CLV in this cycle. Other invariant errors, including `SettlementConflictError`, remain fatal. `persisted_result_count` now counts successful writes rather than fetched payloads.

The regression test reproduces a disputed first fixture and a valid second fixture. It checks failure recording, no stable-result lookup for the disputed fixture, successful persistence of the second fixture, and an accurate persisted count. This establishes local isolation behavior; it does not establish the cause of the live incident or a 24-hour production recovery.

## Release and rollback gate

Before requesting a merge, capture the engine's deployed SHA, last successful result/discovery/registration watermarks, backlog, production failure ledger, and read-only fixture/provider evidence for the disputed ID. Run the full repository test suite, lint and CI on the exact release SHA; inspect the diff for betting and financial contract changes. Identify every Railway service whose watch pattern matches `src/h2h/use_cases/result_settlement.py` and save its prior config and SHA. This PR can trigger production deployment; merge and deployment need owner approval.

After an approved deployment, monitor at least 24 hours: engine process and leadership, discovery and registration watermarks, result backlog, `production_item_failures` for the disputed fixture, settlement counts and P&L reconciliation. Success requires no repeated engine crash from this conflict, unrelated jobs advancing, no new duplicate or incorrect settlement, and the disputed fixture still unresolved until its source evidence is reconciled. Compare source and durable identity manually; never auto-rewrite or delete a result.

Rollback trigger: any incorrect settlement, financial divergence, new invariant failure, or stalled unrelated work. Redeploy the saved previous engine SHA under a separate approved action, preserving DB state and the failure evidence. A code rollback does not undo committed financial facts; stop and reconcile before resuming if those facts diverge.
