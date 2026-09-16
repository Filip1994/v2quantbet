# QuantBet Dashboard Design

> **Status: APPROVED FUTURE DASHBOARD DIRECTION**
>
> This document describes the target dashboard experience. It does **not** describe implemented functionality and must not be read as evidence that any screen, metric, command, or live update exists today.

## Purpose and boundary

The dashboard is a modern, dark-first operational and analytical read view over durable backend state. It is never the source of truth for fixture polling, pick registration, closing capture, settlement, or lifecycle operations. The backend owns the workflow:

`fixture discovery → odds polling → model execution → value/eligibility → immutable pick registration → pick monitoring → closing capture → result acquisition → settlement → CLV`

The dashboard may read durable state and invoke only explicitly supported commands. Closing the browser must not interrupt production work.

## Navigation

Primary navigation is a left rail with: **Live Board**, **Picks**, **Bulletin**, **Performance**, **Fixtures**, **Odds History**, **Models**, **System Health**, and **Settings**. Navigation is blue/neutral and compact; the active destination is unmistakable without relying on color alone.

## Core views

### Live Board

The default view is a dense, readable overview of today's fixtures. Each row should make kickoff, competition, teams, current bookmaker odds, model probabilities, value/edge, fixture state, and active registered-pick state easy to scan. Supported filters are all, live, upcoming, registered picks, detected value, competition, and team search. Selecting a fixture opens a side panel rather than losing board context.

### Fixture detail

The side panel presents fixture identity and kickoff, score/status when applicable, bookmaker odds, model probabilities, implied and de-vig probabilities, edge/value, line movement, supported statistics, model information, and pick state. Missing observations remain visibly missing.

Line movement is first-class and must show the evidence-backed sequence `first seen → pick price → current price → closing price`. A closing price is shown only when a backend closing observation exists; the UI must never fabricate or infer one.

### Picks

Picks are auditable wherever data is available. Detail should include the canonical fixture, competition, kickoff, market, selection, bookmaker, registered odds, registration timestamp, model probability, market/de-vig probability, edge/EV, model/version provenance, current and closing odds, lifecycle, result, settlement, P&L, and realized CLV. Immutable historical facts must not be rewritten to match later observations.

### Bulletin

The bulletin shows final system-selected opportunities with concise reasoning and supporting data. It distinguishes candidate/value opportunity, eligible selection, registered pick, and rejected or filtered opportunity. Selection policy remains backend-defined; the dashboard presents the decision and evidence rather than reimplementing policy.

### Performance

Performance reads durable backend metrics: P&L, ROI, realized CLV, win/loss/push outcomes, time series, and breakdowns by market, competition, bookmaker, and model version. Every metric should have a clear period and evidence boundary.

### System Health

System Health surfaces worker state, last successful polling cycle, API-Football health, odds-ingestion health, database health, historical training/model state, stale warnings, failures/retries, and timestamps. It must not display a generic green “100% healthy” state without evidence.

## Visual language

Use a professional quant/trading-terminal aesthetic, not consumer sportsbook or casino styling:

- Dark-first, information-dense but readable, with strong hierarchy and restrained accents.
- Green means positive/value/healthy; red means negative/error/adverse; blue means navigation or neutral interaction. Status must also have text or shape cues.
- Compact cards and tables, subtle borders/elevation, consistent typography, aligned numeric columns, and clear live/stale/closed indicators.
- Responsive layouts preserve scanability and the fixture detail panel adapts to narrower screens.
- Avoid flashy gradients or glows, gratuitous animation, oversized empty cards, fake live data, and decorative metrics with no backend meaning.

## Operational questions the UX must answer

At a glance, a user should be able to determine: what matches matter; what the model sees; what the market shows; where the edge is; which opportunities became picks; how prices moved; what has closed; how picks settled; how closing-market performance looks; and whether the system is healthy.

## Visual reference and reconstruction note

The approved design reference is a wide desktop dark QuantBet dashboard with a left navigation rail, a top KPI strip, a dense fixture board, a lower picks table, and a right-side fixture/line-movement detail panel. Reconstruct that composition with the principles above if the original image is unavailable: prioritize board density and readable aligned numbers, keep the detail panel contextual, and reserve KPI space for durable backend-derived facts. A future screenshot or reference asset may be stored during dashboard implementation; this markdown is the durable principles/spec and must remain sufficient on its own.

## Non-negotiable integrity rules

1. Backend state and lifecycle operations remain authoritative.
2. The dashboard never invents odds, closing prices, probabilities, health, settlement, or live status.
3. Historical registered-pick facts remain immutable.
4. Unsupported commands are not implied by controls or navigation.
5. Readability and auditability take priority over decoration.
