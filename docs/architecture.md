# Architecture — Working Draft

This document is intentionally a plan, not an implementation.

## Target flow

Provider -> Raw Odds -> Normalizer -> Canonical Quote -> Validation
-> Market Snapshot -> Quant -> Decision -> Risk -> Bet lifecycle -> Settlement

## Odds cadence

Planned cadence from the product requirements:

- Scan fixtures/markets up to 72 hours before kickoff.
- Once an interesting candidate is identified, rescan approximately every 24 hours.
- At 24 hours before kickoff, increase scan frequency.
- At 6 hours before kickoff, increase frequency substantially.
- Exact production intervals will be defined and tested before implementation.

## Bookmakers

Initial supported bookmakers:

- 1xBet
- Bet365
- Superbet

No additional bookmaker should be introduced without an explicit decision.

## Quote semantics

- `first_seen_quote`: first valid quote observed for a fixture/market/selection.
  This is the provisional opening quote because the system does not know the true market opening time.
- `peak_quote`: quote associated with the selected signal/peak opportunity.
- `current_quote`: latest valid quote known to the system.
- `closing_quote`: designated pre-kickoff closing observation.

The exact definitions and database constraints will be implemented later and tested.

## Railway

Railway is the planned runtime platform. The initial target is a small number of services
plus PostgreSQL. We will not introduce additional infrastructure unless a concrete need is proven.
