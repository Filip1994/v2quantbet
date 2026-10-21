# Control Tower snapshot diff

Before `2026-10-01T00:00:00Z` → after `2026-10-02T00:00:00Z`.

Added: 1; absent later: 0; changed: 1. Latest FAILED/CRASHED deployment count: 0 → 1. CI failures in supplied metadata: 0 → 0 (unknown if CI metadata was not supplied).

Retired from registry means absent in the later snapshot, not confirmed deleted. Missing CI/freshness/permission evidence is unknown.

## Added

- `railway:c0aa8208-dd61-48c4-a1d8-488802e84f36:environment-example:new-example`

## Absent later (verify before declaring retired)

- None observed

## Changed

### quantbet-engine

- `source_commit`: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` → `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`
- `last_changed_at`: `2026-09-30T23:00:00Z` → `2026-10-01T23:00:00Z`
- `latest_deployment_status`: `SUCCESS` → `FAILED`
- `operational_state`: `running_instance` → `failed_or_crashed_latest_deployment`
- `running_instances`: `1` → `0`
- Documented reason: reason unknown
