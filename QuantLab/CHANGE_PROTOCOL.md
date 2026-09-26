# QuantLab Change Protocol

Every QuantLab implementation change must update documentation in the same work unit.

Minimum record:

1. Date.
2. Lab or shared core owner.
3. Files/schema changed.
4. What changed.
5. Why it changed.
6. Data sources/endpoints used.
7. API-cost impact.
8. Leakage/provenance considerations.
9. Tests or verification performed.
10. Production impact: normally `NONE`.

## Lab-specific changes

If a feature/model belongs to one laboratory, update that laboratory's README or feature specification as well as `WORKLOG.md`.

## Schema changes

Document table ownership, read/write direction and whether any production table is referenced.

## Model changes

Record model/version identifier and exact feature set. Never silently change the meaning of an existing model version.

## API changes

Record endpoint, cache rule, expected request count and the `quantlab_context` budget effect.
