# QuantBet — Product Goals

_Last synchronized: 2026-09-30_

## 1. Product purpose

QuantBet is a reproducible pre-match football decision system. The product is not merely a prediction model; it must preserve the complete evidence chain from fixture and quote observation through model output, decision, pick, closing reference, result, settlement and research evaluation.

## 2. Production goal

Production should continuously scan the configured future horizon and register only opportunities that pass the active model, market, freshness, eligibility and risk policies.

Required properties:

- deterministic, versioned decision logic;
- canonical fixture/bookmaker/market identities;
- exact quote provenance;
- PostgreSQL durability;
- final quote verification;
- explicit rejection reasons;
- open-exposure protection;
- same-bookmaker monitoring/closing;
- append-only settlement/bankroll evidence;
- fail-closed behavior when required evidence is missing.

## 3. Research goal

Research is a read-only superset of comparable final-gate Production candidates.

Research should answer:

- where model probabilities are calibrated;
- where market disagreement/edge/EV appears persistent;
- how ROI, CLV and calibration behave by bucket;
- whether behavior changes by league, bookmaker, market, time or model/policy regime;
- which candidate rules deserve owner review for Production;
- which Production rules deserve long-horizon review or ban.

Research analytics do not carry automatic Production authority.

## 4. QuantLab goal

QuantLab is the isolated multi-market model laboratory.

Current laboratories:

- GoalLab — goals/BTTS and DC+ Structural;
- CornerLab — corner totals and pressure models;
- CardLab — card/referee models.

QuantLab must preserve timestamp-safe feature provenance and immutable decision evidence while remaining isolated from Production bankroll/registration/model-activation writes.

## 5. Promotion and ban governance

### Promotion

A Research/QuantLab bucket becomes a Production selection rule only through explicit owner approval.

Forward/OOS confirmation is useful and should be shown when available, but it is not a mandatory owner-approval gate.

### Ban

A performance-based permanent ban should normally require **3–6 months** of observation. Short-term variance alone is not enough.

Technical-integrity failures may be suspended immediately.

## 6. Performance evidence

Never interpret ROI alone.

Important evidence includes:

- settled N;
- price/odds distribution;
- win rate and uncertainty;
- model-vs-realized calibration;
- CLV coverage and direction;
- bookmaker consistency;
- league breadth;
- temporal stability;
- model/policy regime.

Profitability claims require representative evidence; operational success is not proof of edge.

## 7. Infrastructure goal

- GitHub for source/CI.
- Railway services for runtime.
- PostgreSQL as canonical durable state.
- No silent SQLite production fallback.
- Provider budgets and retries are explicit product constraints.
- Historical decision evidence remains reconstructable.

## 8. Dashboard goal

Dashboards are operational/research views over durable facts.

The UI should make it easy to answer:

- what is active now;
- why a pick exists;
- which price/model/policy produced it;
- what happened after registration;
- where coverage is lost;
- which research buckets are interesting;
- exactly which picks belong to a cohort.

## 9. Current strategic direction

Do not redesign the universe.

The current focus is:

1. release discipline;
2. model/data coverage;
3. research/analytics evidence quality;
4. maintainability of the largest modules.

See [CURRENT_PRIORITIES.md](./CURRENT_PRIORITIES.md).
