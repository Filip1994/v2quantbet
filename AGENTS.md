For user requests to VOID Production picks or clear Production history, follow
`docs/PRODUCTION_OPERATIONS.md` and `scripts/manage_production_picks.py`.
Use the Production-only overrides; preserve Research and provider facts.
Skipping a Production pick must exclude it from active picks and history while
retaining its immutable clone identity so synchronization cannot reintroduce it.
