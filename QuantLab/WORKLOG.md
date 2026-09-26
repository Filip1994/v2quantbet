# QuantLab Work Log

This is the canonical chronological record of QuantLab implementation work.

## 2026-09-26 — Foundation and isolation

**Owner:** QuantLab core

### Completed

- Created separate Railway service `quantbet-quantlab`.
- Created three dashboard laboratories: GoalLab, CornerLab and CardLab.
- Added shared shadow-bet ledger `quantlab_shadow_bets`.
- Restricted initial bookmakers to Bet365 (8) and 1xBet (11).
- Added `quantlab_context` provider request category.
- Set QuantLab API budget target/hard ceiling to 1,000 requests/day at the QuantLab service boundary.
- Dashboard reports shadow bets, settled count, P&L, ROI, win rate, average CLV, max drawdown and QuantLab API usage.
- Blocked QuantLab from production write responsibilities by architecture.
- Refactored runtime ownership into `src/h2h/quantlab/`.
- Added top-level `QuantLab/` architecture documentation and separate GoalLab/CornerLab/CardLab specifications.

### API impact

Foundation itself adds no recurring provider calls. Future ingestion must use `quantlab_context`.

### Production impact

No production-model or bankroll/pick-registration behavior is changed by this refactor.

### Next implementation target

All-market Bet365 + 1xBet QuantLab ingestion, followed by CardLab v1 feature acquisition/derivation.

## 2026-09-26 — Next task frozen

**Owner:** QuantLab core

Created `QuantLab/TASKS/001_MARKET_COLLECTOR_CARDLAB_V1.md` as the canonical next implementation task. It covers Bet365/1xBet all-market ingestion, lab classification and CardLab v1 context features while preserving production isolation.
