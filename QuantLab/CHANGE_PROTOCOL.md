# QuantLab Change Protocol

_Last synchronized: 2026-09-30_

1. Preserve QuantLab/Production write isolation.
2. Every probability/model semantic change requires an explicit version change.
3. Every pre-match feature must be timestamp-safe and reconstructable.
4. Historical decisions/picks/settlements are append-only evidence.
5. Do not silently change settlement semantics.
6. Do not silently reuse approval across a changed immutable model hash where exact-hash authority applies.
7. Update the relevant Lab README and [WORKLOG.md](./WORKLOG.md) for material implementation changes.
8. Update [../docs/CURRENT_PRIORITIES.md](../docs/CURRENT_PRIORITIES.md) only when project priorities/governance change.
9. QuantLab analytics may discover candidate Production rules, but cannot apply them automatically.
10. Production promotion requires explicit owner approval; a fixed forward/OOS waiting period is not mandatory.
