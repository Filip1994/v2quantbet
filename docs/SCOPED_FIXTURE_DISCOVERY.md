# Scoped Fixture Discovery

## Status

Implemented in the application layer. The use-case composes the provider-neutral `FixtureDiscovery` port with the Phase I competition-scope policy.

## Flow

```text
provider adapter
    -> FixtureDiscovery.discover(start_at, end_at)
    -> ScopedFixtureDiscovery
    -> classify_phase_i(competition metadata)
    -> tuple[Fixture, ...]
```

## Behavior

- Rejects an invalid discovery window when `start_at >= end_at`.
- Delegates the exact requested window to the underlying discovery port.
- Converts the returned sequence into a tuple.
- Preserves the provider result order for eligible fixtures.
- Applies the existing fail-closed Phase I competition policy.
- Does not perform HTTP, authentication, pagination, persistence, or model-probability calculation.

## Important boundary

`ScopedFixtureDiscovery` filters the canonical fixture universe. It does not decide whether a fixture has betting value. Value evaluation remains a separate step based on model probability and canonical bookmaker quotes.

## Verification

Unit tests cover:

- eligible and out-of-scope competitions;
- delegation of the requested time window;
- order preservation and tuple output;
- invalid and equal time windows.

CI status must be verified against the GitHub Actions run for the relevant commit before this work is marked production-ready.
