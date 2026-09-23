# Value pick evaluation

## Multi-bookmaker execution

One persisted model prediction evaluates every fresh, complete approved-book observation.
Eligible evaluations are grouped by exact market and outcome, ranked by decimal odds, and
final-verified in that order. The final refreshed price is evaluated again. Registration
therefore freezes bookmaker, odds, source, snapshot, model probability, edge and EV together;
existing duplicate and exposure constraints still decide whether the pick can be accepted.

## Purpose

Ovaj sloj direktno poredi verovatnoću koju daje model sa cenom koju nudi bookmaker. Ne odlučuje o profitabilnosti sistema i ne uvodi dodatne heuristike.

## Formule

Za decimalnu kvotu `odd` i modelsku verovatnoću `p`:

- `implied_probability = 1 / odd`
- `probability_gap = p - implied_probability`
- `expected_value = p * odd - 1`

Primer: `p = 0.70`, `odd = 1.90`:

- implied probability: `52.63%`
- probability gap: `+17.37` procentnih poena
- expected value: `+0.33` odnosno `+33%` po jedinici uloga

## Granice

- Model probability mora biti u intervalu `[0, 1]`.
- Quote ostaje canonical domain objekat; evaluator ga ne menja.
- Rezultat je immutable `ValuePick`.
- Rangiranje, bulletin format i izbor maksimalnog broja pickova dolaze u sledećem vertical slice-u.
