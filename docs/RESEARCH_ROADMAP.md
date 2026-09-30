# QuantBet Research Roadmap

**Status:** Operational — no longer a deferred side project  
**Last synchronized:** 2026-09-30

## Current foundation

Research already has:

- canonical final-gate candidate capture;
- PLAYED / SKIPPED / BLOCKED_EXPOSURE routes;
- immutable decision context;
- raw model probability, market fair probability, edge, EV and odds;
- settlement linkage;
- same-book closing/CLV when available;
- bucket/cohort analytics;
- model/policy regime dimensions;
- time-sliced stability views;
- drilldowns to exact picks.

## Roadmap

### 1. Evidence quality

Add stronger uncertainty and stability reporting:

- ROI confidence/uncertainty interval;
- 30/60/90-day stability;
- league breadth;
- bookmaker consistency;
- regime consistency.

### 2. Coverage diagnostics

Expose why candidates disappear from the funnel:

```text
discovered
→ modelable
→ quote eligible
→ value evaluated
→ final-gate research candidate
→ Production / blocked / skipped
```

### 3. Owner review workflow

Research should make candidate Production rules easy to inspect, but it must not auto-promote them.

The owner may approve a bucket without a mandatory forward/OOS waiting period. When forward evidence exists, show it separately from discovery history.

### 4. Ban monitoring

For existing Production buckets, maintain enough evidence to support a deliberate 3–6 month performance review.

Immediate suspension remains reserved for technical-integrity failures.

### 5. Long-term archive/analytics

As data volume grows, retain the option to introduce object-storage/columnar archival for raw historical payloads. PostgreSQL remains the current canonical operational database; archive infrastructure should be added only when scale justifies it.
