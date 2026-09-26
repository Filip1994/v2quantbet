# CardLab

CardLab owns QuantLab experiments for cards, bookings and fouls.

## CardLab v1

CardLab v1 starts with team card/foul profiles and the five match-context variables requested for immediate use:

1. referee card rate
2. referee foul rate
3. derby/rivalry indicator
4. table pressure
5. match importance

See [FEATURES_V1.md](./FEATURES_V1.md) for the initial contract.

## Separation

These five context variables are CardLab-owned in v1. They are not inputs to GoalLab/DC+ or CornerLab unless a later separately-versioned experiment explicitly tests that change.

## Settlement warning

Provider markets such as cards, bookings and booking points can have different settlement semantics. Raw provider bet ID/name/selection and line must be preserved. No generic "cards" settlement rule may be assumed.
