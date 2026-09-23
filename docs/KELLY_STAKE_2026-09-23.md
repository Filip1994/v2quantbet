# Kelly Stake — calibrated fractional Kelly idea

**Date:** 2026-09-23  
**Status:** Research / future staking design  
**Current production staking:** Fixed stake  
**Repository:** QuantBet V2

## Purpose

Preserve the idea for a future staking engine once QuantBet has enough real production picks, settlements, CLV observations, and calibration data.

The current production system should remain on a fixed stake during the initial live rollout. The purpose is to collect a clean sample of real decisions without allowing a dynamic staking algorithm to distort the evaluation of model quality.

## Core idea

Do not apply Kelly Criterion mechanically to the raw model probability or raw expected value.

Instead, build a **calibrated fractional Kelly** staking layer that learns which kinds of signals have actually been reliable in production.

Example:

- EV 6–7% may prove historically more reliable than EV 8–9%.
- If the 6–7% bucket has stronger realized ROI, better calibration, stronger CLV, and sufficient sample size, it may deserve a larger stake.
- If the 8–9% bucket is historically overconfident or unstable, it may deserve a smaller stake even though its raw model EV is higher.

Therefore:

> Higher raw EV must not automatically imply a higher stake.

The stake should depend on the empirically demonstrated reliability of the signal.

## Intended future flow

```text
raw model probability
        ↓
raw edge / expected value
        ↓
historical calibration layer
        ↓
adjusted probability / confidence
        ↓
fractional Kelly
        ↓
confidence multiplier
        ↓
hard stake caps
        ↓
final stake
```

## Calibration layer

Before Kelly sizing, QuantBet should evaluate how reliable each signal family has been historically.

Candidate dimensions include:

- expected-value bucket;
- edge bucket;
- market;
- competition / league;
- bookmaker;
- odds range;
- time-to-kickoff;
- model version;
- quote freshness / data-quality flags;
- CLV behavior;
- relevant combinations of the above, only where sample size is sufficient.

The calibration layer should avoid treating a small winning streak as evidence.

## Example

Suppose historical production data shows:

```text
EV 2–4%   → weak realized performance
EV 4–6%   → acceptable
EV 6–7%   → strongest and most stable calibration / ROI / CLV
EV 8–10%  → weaker than the model predicts
```

Then staking should not simply increase with raw EV.

Illustrative future behavior:

```text
raw quarter-Kelly stake = 500 RSD

EV 6–7% bucket
historically strong and stable
confidence multiplier = 1.00
final before caps = 500 RSD

EV 8–10% bucket
historically overconfident
confidence multiplier = 0.55
final before caps = 275 RSD
```

The exact multipliers must be learned and validated from data rather than hard-coded from this example.

## Metrics to evaluate before production use

Do not design the Kelly layer from win rate alone.

At minimum evaluate:

- realized ROI;
- realized P&L;
- model calibration;
- predicted probability vs observed hit rate;
- realized CLV;
- sample size;
- variance;
- drawdown;
- odds buckets;
- EV buckets;
- edge buckets;
- market-level stability;
- league-level stability;
- out-of-sample performance;
- walk-forward performance.

## Probability calibration

If the model systematically overestimates or underestimates probability in a segment, Kelly must not use the uncorrected raw probability.

Example:

```text
model probability ≈ 64%
observed long-run hit rate ≈ 59%
```

A future staking engine should use a calibrated / shrunk estimate rather than blindly using 64%.

This is important because Kelly becomes most aggressive precisely where probability estimates appear strongest. If those estimates are overconfident, staking risk is amplified.

## Preferred staking architecture

Future target:

```text
Calibrated Probability
        +
Empirical Confidence Multiplier
        +
Fractional Kelly
        +
Hard Risk Caps
        =
Final Stake
```

Potentially use quarter-Kelly or another conservative fractional Kelly as the starting research baseline rather than full Kelly.

Full Kelly should not be the default production choice.

## Hard safety constraints

Any future dynamic staking implementation should preserve hard risk controls.

Examples:

- maximum stake per pick;
- maximum percentage of bankroll per pick;
- maximum open exposure;
- duplicate fixture / market protection;
- bankroll availability;
- optional league / market caps;
- no stake increase based only on a tiny sample;
- no automatic promotion from research to production.

## Current decision

For the initial live production phase:

- keep fixed staking;
- collect real picks;
- collect settlements;
- collect CLV;
- measure calibration;
- avoid changing stake sizing after a small number of wins or losses.

The Kelly idea should only move toward production after QuantBet has a sufficiently large and trustworthy sample and after the calibration layer is tested out-of-sample / walk-forward.

## Research promotion boundary

A future Kelly staking system should follow:

```text
production data collection
→ calibration analysis
→ historical simulation
→ fractional Kelly comparison
→ drawdown / risk analysis
→ out-of-sample or walk-forward validation
→ documented acceptance decision
→ production implementation
```

This document records the concept only. It does not change current production staking behavior.
