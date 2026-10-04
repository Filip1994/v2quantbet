# QuantLab Operations — Lab Kill Switches

## Purpose

QuantLab exposes four independent environment-variable kill switches so one research branch can be stopped immediately without deleting data, changing schema, or disabling the read-only dashboard.

| Branch | Variable | Default | Production state after 2026-10-04 change |
| --- | --- | --- | --- |
| GoalLab | `QUANTBET_QUANTLAB_GOAL_ENABLED` | `true` | `true` |
| CornerLab | `QUANTBET_QUANTLAB_CORNER_ENABLED` | `true` | `true` |
| CardLab | `QUANTBET_QUANTLAB_CARD_ENABLED` | `true` | `false` |
| H2HLab | `QUANTBET_QUANTLAB_H2H_ENABLED` | `true` | `true` |

Accepted boolean values are `1/true/yes/on` and `0/false/no/off`.

## Semantics

A disabled branch performs no new branch-specific:

- shadow evaluation or pick creation;
- provider-backed result refresh;
- settlement work;
- branch-specific history/bootstrap collection;
- CardLab referee web/history/event collection when CardLab is disabled;
- H2H snapshot acquisition and paired-experiment processing when H2HLab is disabled;
- offline modeler/audit work for GoalLab, CornerLab, or CardLab.

Persisted history remains available to the dashboard and analytics.

## Shared upstream dependencies

The market collector is dependency-aware:

- GoalLab and H2HLab share GOAL markets (OU 2.5 / BTTS). If either is enabled, GOAL market collection remains active.
- CornerLab and CardLab share the broad context fixture queue, but market rows are retained only for enabled labs.
- Generic fixture discovery runs while at least one lab is enabled.
- Generic historical-statistics backfill runs only while GoalLab, CornerLab, or CardLab is enabled.
- CardLab-specific context/referee work is skipped when CardLab is disabled.

This prevents disabling GoalLab from accidentally starving H2HLab, while still allowing CardLab to be stopped cleanly.

## Operational procedure

To stop one branch, set its variable to `false` on every QuantLab runtime service that can execute work, especially:

- `quantbet-quantlab-collector`;
- `quantbet-quantlab-modeler`;
- any alternate/one-shot QuantLab collector service.

Keep the same values on the dashboard service for configuration consistency.

To restore a branch, set its variable back to `true`. No database repair or replay is required; normal TTL/watermark rules resume from persisted state.

## Verification

Collector logs emit this line at the start of every cycle:

`QuantLab lab switches goal=<...> corner=<...> card=<...> h2h=<...>`

The modeler emits the same effective state on each run. A disabled branch should remain at zero in the cycle-completion counters.
