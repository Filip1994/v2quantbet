# GoalLab

GoalLab owns QuantLab experiments for goals and BTTS.

## Initial model family

`DC+ Core` keeps current Dixon-Coles as the control/base and tests incremental structural features:

- recent goals for/against
- recent points/form
- home/away splits
- rest-day differential
- fixture congestion

Market-aware variants must be evaluated separately from structural DC+ so that market information is not silently mixed into an independent sports probability model.

## Markets

GoalLab may ingest all Bet365/1xBet goal-related markets, while canonical modeling/settlement support is added explicitly and versioned.

## Referee variables

Referee card/foul variables do **not** belong to GoalLab v1.
