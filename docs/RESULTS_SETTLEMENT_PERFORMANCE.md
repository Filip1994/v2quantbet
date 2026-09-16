# Results, settlement, bankroll release, P&L, and realized CLV

Task #12 adds an append-only production result and financial lifecycle to durable registered
picks. API-Football result records are content-addressed and retain their normalized score
breakdown plus canonical provider JSON. Operational polling state is mutable; result,
settlement, ledger, and realized-CLV facts are immutable.

The settlement rule is `SETTLEMENT_OU25_BTTS_REGULATION_V1`. `FT`, `AET`, and `PEN` use only
`score.fulltime` for the existing OU 2.5 and BTTS markets. Stable `CANC`, `ABD`, `AWD`, and
`WO` observations void a pick. Other, unknown, or malformed states do not settle.

A result is eligible only after two matching terminal confirmations separated by the configured
finality delay. Normal settlement and its ledger effect commit atomically. Entry odds cross the
money boundary as PostgreSQL text to `Decimal`; gross return is rounded to integer minor units
with `ROUND_HALF_UP` under `MONEY_HALF_UP_V1`.

Realized CLV is persisted only for a valid immutable Closing in the same series/source context
and with the same kickoff as the result used for settlement. `CLV_ODDS_RATIO_PPM_V1` stores
`ROUND_HALF_UP((Entry / Closing - 1) * 1,000,000)`. Missing, stale, provenance-conflicting, or
post-reschedule Closing data remains explicitly unavailable.

Later provider observations may flag `CORRECTION_REQUIRED`, but ordinary ingestion never
changes committed settlement or ledger rows. The settlement event schema supports explicit
append-only `CORRECTION` and `REVERSAL` successors without an operator UI.
