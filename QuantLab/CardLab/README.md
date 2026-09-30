# CardLab

_Last synchronized: 2026-09-30_

CardLab owns QuantLab experiments for cards, bookings, fouls and referee/context effects.

## Current canonical path

- decision policy family: `CARDLAB_1XBET_POISSON_POLICY_V5_MARKET80`
- probability model: `CARDLAB_REFEREE_POISSON_V1`
- canonical market: API-Football bet ID 80, 1xBet `Cards Over/Under`
- Bet365 is not an active CardLab probability/reference/PICK source.

Current lambda is derived from historical referee card rate with a minimum referee-history requirement.

## Current data constraint

The current practical blocker is **referee-history coverage**.

A large share of eligible fixtures can fail because there is not enough trustworthy referee history.

Therefore the immediate CardLab priority is data coverage and statistical reliability, not feature-count growth.

## Next model work

After data coverage improves:

- shrink referee rates toward league baselines;
- evaluate hierarchical/partial-pooling alternatives;
- add team/league discipline context only with timestamp-safe evidence;
- measure whether derby/table-pressure/match-importance variables add out-of-sample information before giving them model authority.

## Settlement

Current canonical settlement reconstructs player card events from the provider under the versioned CardLab semantics.

Ambiguous markets such as booking points, team-only cards, halves and card handicaps remain excluded until their settlement meaning is explicitly canonicalized.

## Production boundary

CardLab is QuantLab-only. It does not write Production picks, bankroll or active Production model state.
