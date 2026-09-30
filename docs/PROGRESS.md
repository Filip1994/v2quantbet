# QuantBet — Progress

> **Current-state rule:** this file is a concise milestone log. Use [../PROJECT_STATUS.md](../PROJECT_STATUS.md) for the current snapshot and [CURRENT_PRIORITIES.md](./CURRENT_PRIORITIES.md) for the active queue.

## 2026-09-30 — universe/documentation sync

- Production, Research and QuantLab are now documented as three separate but connected sectors.
- Research Analytics V2 and QuantLab GoalLab/CornerLab Watchlist analytics are part of the current universe.
- Stale claims that Research is a future side project, that model lifecycle is unimplemented, or that the bulletin-to-settlement path is incomplete are superseded.
- Bucket governance is explicit:
  - owner approval is required for Production promotion;
  - forward/OOS evidence is advisory rather than a mandatory promotion gate;
  - permanent performance-based bans default to a 3–6 month review horizon;
  - technical-integrity failures can be suspended immediately.
- Documentation now has a canonical status/index layer so dated audits and Task files cannot be mistaken for current state.

## 2026-09-29/30 — QuantLab analytics expansion

- Added deeper measurable bucket dimensions for GoalLab and CornerLab.
- Promoted the highest-value cross-feature views into **Watchlist · ROI discovery**.
- Added exact bucket drilldowns to the underlying settled picks.
- Added sortable analytics table headers.
- Removed duplicate/noisy analytics tables from the main operator flow.
- Added GoalLab derived lambda/balance/trend/matchup/reliability dimensions.
- Added CornerLab model-line/pressure/trend/matchup/reliability dimensions.

## GoalLab V2 remediation

- Replaced the V1 dimensionality explosion with a compact predeclared structural feature contract.
- Added minimum feature-observation requirements, ridge regularization and train-fold preprocessing.
- Preserved strict pre-match timestamp/leakage rules.
- Added chronological DC-vs-DC+ validation and exact-model-hash manual authority.

## CornerLab V2

- Replaced the cross-book reference as the active probability source with the pressure-Poisson structural model.
- Bookmaker odds remain outside the probability model.
- Historical audit tracks calibration/error/dispersion.
- Current practical constraint is data/team-history coverage.

## CardLab

- Current path is referee-Poisson for 1xBet Cards Over/Under.
- Referee-history coverage is currently the main blocker.
- The immediate priority is better data coverage and semantics, not a wider dashboard/model surface.

## Production and Research foundation

The production path from discovery through registration, monitoring, closing, settlement and bankroll accounting is implemented and running. Research captures comparable final-gate candidates and provides read-only cohort analytics without mutating Production.

Older detailed engineering chronology remains available in Git history and dated audit/worklog documents.
