# Control Tower snapshot diff

Before `2026-10-10T01:47:58Z` → after `2026-10-10T09:50:02Z`.

Added: 0; absent later: 0; changed: 2. Latest FAILED/CRASHED deployment count: 1 → 2. CI failures in supplied metadata: 1 → 1 (unknown if CI metadata was not supplied).

Retired from registry means absent in the later snapshot, not confirmed deleted. Missing CI/freshness/permission evidence is unknown.

## Added

- None observed

## Absent later (verify before declaring retired)

- None observed

## Changed

### quantbet-baseball-cold-storage

- `latest_deployment_status`: `SUCCESS` → `CRASHED`
- `operational_state`: `scheduled_cron_current_run_unknown` → `failed_or_crashed_latest_deployment`
- Documented reason: reason unknown

### quantbet-quantlab-collector

- `running_instances`: `1` → `0`
- Documented reason: reason unknown
