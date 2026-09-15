# Architecture — Working Draft

This document is intentionally a plan, not an implementation.

## Target flow

Provider -> Raw Odds -> Normalizer -> Canonical Quote -> Validation
-> Market Snapshot -> Quant -> Decision -> Risk -> Bet lifecycle -> Settlement

## Odds cadence

The agreed product policy is deliberately conservative and separates fixture discovery from quote refresh:

- **Fixture discovery:** scan fixtures and markets up to **72 hours before kickoff**, approximately every **15 minutes**.
- **Early quote refresh (T−72h to T−48h):** approximately once per day.
- **T−48h to T−24h:** approximately every **12 hours**.
- **T−24h to T−6h:** approximately every **6 hours**.
- **T−6h to T−2h:** approximately every **2 hours**.
- **T−2h to kickoff:** approximately every **30 minutes**.
- **T−15 minutes:** perform a dedicated final/closing capture.

These are the agreed baseline intervals, not a mandate to refresh every fixture indiscriminately. Quote refresh is selective and should focus on relevant fixtures, markets, and bookmaker sources. Discovery must not automatically trigger a full quote collection for every discovered fixture.

The system must preserve the distinction between:

- inexpensive fixture discovery;
- selective quote refresh;
- intensified monitoring only for fixtures with meaningful betting potential;
- the dedicated pre-kickoff closing capture.

The previous global 60-second quote-polling approach is **not** the agreed policy.

## Bookmakers

Initial supported bookmakers:

- 1xBet
- Bet365
- Superbet

No additional bookmaker should be introduced without an explicit decision.

## Quote semantics

- `first_seen_quote`: first valid quote observed for a fixture/market/selection.
  This is the provisional opening quote because the system does not know the true market opening time.
- `pick_quote`: valid quote captured at the moment the bulletin/tip is published.
  This is the actual offered price used as the reference for the pick.
- `current_quote`: latest valid quote known to the system.
- `closing_quote`: designated pre-kickoff closing observation.

The exact definitions and database constraints will be implemented later and tested.

## Railway

Railway is the planned runtime platform. The initial target is a small number of services
plus PostgreSQL. We will not introduce additional infrastructure unless a concrete need is proven.
