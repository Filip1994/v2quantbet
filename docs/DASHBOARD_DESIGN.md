# QuantBet Dashboard Design

> **Status: living design direction with implemented Production/Research/QuantLab surfaces.**  
> _Last synchronized: 2026-09-30_

## Design objective

The dashboard family should make dense quantitative evidence easy to scan without hiding provenance.

## Production visual priorities

- fixture and market identity first;
- Pick/current/best/closing odds clearly separated;
- model vs market probability;
- edge / EV;
- operator state;
- result / P&L / CLV;
- worker/model/provider health.

## Research visual priorities

Research should prioritize evidence, not decoration:

- N;
- cohort definition;
- ROI/P&L;
- calibration;
- CLV;
- time/model/policy regime;
- direct link to exact constituent picks.

## QuantLab visual priorities

GoalLab/CornerLab Analytics should keep the Watchlist first.

Watchlist titles must describe the cross being measured. Bucket names should be clickable to their underlying picks. Sorting should work directly from table headers.

Avoid duplicated tables and raw-feature table spam when a more decision-useful derived view exists.

## Integrity

- never invent missing data;
- keep missingness distinguishable from zero;
- never imply automatic Production authority;
- never show a green health state without backend evidence;
- keep current/historical/model-policy regime boundaries visible.

## Direction

The preferred design remains a dense dark desktop quantitative interface with strong table legibility, clear status badges and minimal navigation loss between a cohort and its exact evidence.
