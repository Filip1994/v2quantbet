# QuantLab

QuantLab is QuantBet's isolated multi-market model laboratory.

It is **not** the existing Research Board and it has **no authority to place production bets**.

## Laboratories

- [GoalLab](./GoalLab/README.md) — goals, BTTS and DC+ experiments.
- [CornerLab](./CornerLab/README.md) — corner totals, team corners and corner handicaps.
- [CardLab](./CardLab/README.md) — cards, fouls, referee and match-context models.

## Runtime

Runtime code lives under `src/h2h/quantlab/`. This top-level `QuantLab/` directory is the canonical architecture, experiment and work-log record.

## Hard boundaries

1. Production registration, bankroll, pick decisions and active production model activation are out of bounds.
2. QuantLab predictions are shadow-only until separately promoted through an explicit future production decision.
3. Bet365 (API-Football bookmaker 8) and 1xBet (11) are the initial market universe.
4. QuantLab API usage is a separate `quantlab_context` category with a 1,000 request/day hard ceiling.
5. Every feature must record provenance and availability time before it can be used for historical evaluation.
6. Every implementation change must be recorded in [WORKLOG.md](./WORKLOG.md).

See [ARCHITECTURE.md](./ARCHITECTURE.md) and [CHANGE_PROTOCOL.md](./CHANGE_PROTOCOL.md).
