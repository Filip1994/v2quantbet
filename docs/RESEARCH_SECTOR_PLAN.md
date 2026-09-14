# QuantBet — Research Sector Plan

## 1. Purpose

Research is the analytical and experimental layer of QuantBet. It does not search for today's picks and it does not directly control the Daily Bulletin. Its purpose is to establish whether production signals are calibrated, robust, economically meaningful, and reproducible.

The central research question is:

> Under which measurable conditions should QuantBet trust, downgrade, or reject a detected value signal?

## 2. Separation from Daily Bulletin screening

### Daily Bulletin screening

The production screening pipeline answers:

> Which upcoming fixtures currently show the strongest eligible model-vs-bookmaker value?

It uses current data, fixed production rules, and deterministic ranking.

### Research

Research answers:

> Why does this signal appear, how often is it reliable, and does it generalize beyond the observed sample?

It uses historical snapshots, outcomes, versioned experiments, and statistical validation.

Research must never silently change production behavior.

## 3. Research data foundation

Research requires historically reconstructable data. The system must preserve:

- raw provider observations;
- normalized fixture, market, selection, and odds records;
- model probabilities with model and configuration versions;
- immutable pick decision contexts;
- timestamped odds snapshots;
- first-seen, pick-time, current, and closing references;
- final match results and settlement state;
- contextual observations such as lineups, injuries, and weather when available.

Derived metrics must not replace raw observations. Every research result must be traceable to source records.

## 4. Research workstreams

### 4.1 Calibration

Measure whether predicted probabilities correspond to observed frequencies.

Required analyses:

- reliability curves;
- Brier score and log loss where applicable;
- calibration by market and competition;
- systematic overconfidence or underconfidence;
- calibration drift over time;
- sample-size and uncertainty reporting.

### 4.2 Value-signal quality

Study whether larger probability gaps correspond to better outcomes or better market information.

Required analyses:

- distribution of probability gaps;
- signal frequency by market and competition;
- realized outcomes grouped by gap buckets;
- extreme-gap outlier review;
- data-quality and stale-odds rejection analysis;
- false-positive and false-negative review.

### 4.3 Odds movement and CLV

Study the relationship between the odds available at decision time and subsequent market movement.

Required analyses:

- pick odds versus closing reference;
- time-to-kickoff movement curves;
- bookmaker-specific movement;
- disagreement between bookmakers;
- realized CLV by market, competition, and signal strength;
- missing, stale, or invalid closing-reference rates.

Expected CLV must remain separate from realized CLV and must be versioned independently.

### 4.4 Contextual factors

Evaluate whether additional information improves reliability without introducing leakage.

Candidate factors include:

- confirmed lineups;
- injuries and suspensions;
- weather;
- rest days and congestion;
- bookmaker disagreement;
- odds movement velocity;
- time to kickoff;
- competition and team-strength segments.

Every factor must be evaluated with an explicit availability timestamp. Information unavailable at decision time cannot be used in a historical decision simulation.

### 4.5 Model and rule experiments

Compare model versions, feature sets, thresholds, and ranking rules through controlled experiments.

Each experiment must define:

- hypothesis;
- baseline;
- dataset and time period;
- inclusion/exclusion rules;
- feature and model versions;
- evaluation metrics;
- leakage controls;
- stopping or acceptance criteria;
- result and limitations.

## 5. Experiment lifecycle

```text
hypothesis
→ experiment specification
→ immutable dataset selection
→ baseline definition
→ implementation
→ backtest
→ out-of-sample or walk-forward evaluation
→ robustness checks
→ result report
→ explicit accept/reject decision
```

An experiment is not valid merely because it improves an in-sample metric.

## 6. Required methodological controls

Research must explicitly address:

- look-ahead and target leakage;
- survivorship bias;
- selection bias from only examining published picks;
- missing-data bias;
- stale or duplicated odds;
- bookmaker availability bias;
- multiple testing;
- overfitting and p-hacking;
- temporal dependence;
- regime and competition drift;
- uncertainty caused by small samples.

Where possible, evaluation should use chronological splits and walk-forward validation rather than random shuffling.

## 7. Research outputs

Research may produce:

- calibration reports;
- value-signal reports;
- CLV and odds-movement reports;
- experiment specifications;
- reproducible datasets;
- backtest results;
- model/rule proposals;
- production-promotion recommendations;
- documented rejected hypotheses and limitations.

Every output must state its data period, sample size, methodology version, and limitations.

## 8. Promotion to production

A research result becomes a production candidate only after:

1. the experiment is reproducible;
2. the baseline is explicit;
3. out-of-sample or walk-forward results are available;
4. leakage and bias checks are documented;
5. robustness across relevant segments is assessed;
6. the economic and operational impact is understood;
7. the proposed production change is reviewed and explicitly implemented;
8. regression tests and CI verification pass.

There is no automatic promotion from Research to production.

## 9. Implementation order

Research should be implemented only after the production data foundation is sufficiently stable. The planned order is:

1. immutable odds and decision-context history;
2. outcome and settlement linkage;
3. reproducible analytical dataset export;
4. baseline calibration report;
5. baseline value-signal report;
6. odds movement and realized-CLV analysis;
7. walk-forward backtesting framework;
8. contextual-factor experiments;
9. model/rule version comparison;
10. controlled promotion workflow.

## 10. Definition of done

The Research sector is operational only when a researcher can reproduce a reported result from stored source records, identify the exact model/data versions used, distinguish in-sample from out-of-sample evidence, and produce an explicit recommendation without modifying production logic implicitly.
