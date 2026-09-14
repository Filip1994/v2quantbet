# QuantBet — Product Goals

## 1. Product purpose

QuantBet is a production football value-betting system. Its purpose is to continuously scan upcoming matches, evaluate bookmaker odds against quantitative model probabilities, identify value opportunities, and track the market before and after a pick is made.

The system must be designed for reproducibility, traceability, and measurable performance—not only for producing isolated predictions.

## 2. Match horizon

- Scan all relevant matches scheduled within the next **72 hours**.
- Continuously update the available match and market universe as fixtures and odds change.
- Keep all timestamps in a consistent, explicitly defined timezone strategy.

## 3. Odds ingestion and market history

The system must ingest bookmaker odds and preserve their history rather than only the latest value.

Every odds snapshot must include, at minimum:

- match/fixture identifier;
- bookmaker identifier;
- market and selection identifier;
- odds value;
- capture timestamp;
- source and ingestion metadata where available.

The system must support reconstruction of the odds state at any relevant point in time.

## 4. Quantitative value signal

For each supported market:

1. Calculate the model probability.
2. Calculate the bookmaker-implied probability.
3. Compare the two probabilities.
4. Identify a value opportunity when the model probability exceeds the bookmaker-implied probability, subject to configured filters and risk controls.

The value signal must be kept separate from predictions about future odds movement and from post-event performance evaluation.

## 5. Expected CLV signal

Before the event starts, the system may estimate whether the selected odds are likely to move in a favorable direction before the closing line is established.

This is a separate, optional signal from model-vs-bookmaker value:

- **Value** measures the discrepancy between model probability and bookmaker-implied probability at decision time.
- **Expected CLV** estimates the likely direction and magnitude of subsequent market movement before the event starts.
- **Realized CLV** is calculated later, using the actual closing reference observed for the market.

A value opportunity must not automatically be described as a positive expected-CLV opportunity without a separate, versioned methodology and supporting data.

## 6. Pick registry

Every published pick must be registered with immutable decision context, including:

- pick identifier;
- fixture and market/selection;
- model version and configuration;
- model probability;
- bookmaker-implied probability;
- value calculation;
- expected-CLV signal and methodology version, where available;
- odds at pick time;
- pick timestamp;
- applicable filters and decision metadata.

## 7. Post-pick monitoring and realized CLV

After a pick is published, the system must continue collecting and evaluating odds until the event starts or the monitoring window ends.

The monitoring design must support a configurable cadence. An initial candidate cadence is every **30 minutes**, but the final cadence must be defined by system requirements and operational constraints.

The system must record the odds trajectory after publication. **Realized CLV must be calculated after the relevant event has finished**, once the system has a valid closing reference and the market outcome/settlement state is available as required by the selected CLV definition.

The realized-CLV calculation must use the actual pick-time odds and the actual closing reference, preserve the calculation methodology/version, and remain distinguishable from expected CLV.

## 8. Required odds checkpoints

The dashboard and reporting layer must expose, at minimum, these checkpoints for every tracked pick:

- **First seen odds** — the earliest captured odds for the relevant quote;
- **Pick odds** — the odds at the moment the pick was published;
- **Current odds** — the latest captured odds;
- **Closing odds** — the last valid captured odds before the match starts, used as the closing reference for realized CLV where valid.

Each checkpoint must be timestamped and traceable to the underlying odds snapshot.

## 9. Daily bulletin

After midnight, the system must produce a daily bulletin containing the best current value opportunities for the configured future horizon.

The bulletin should include, at minimum:

- fixture and kickoff time;
- bookmaker and market/selection;
- current odds;
- model probability;
- implied probability;
- value estimate;
- expected-CLV signal, where available;
- relevant confidence, filtering, and data-quality indicators.

The bulletin must clearly distinguish opportunities that are currently actionable from historical, already published, or expired picks.

The operational screening flow is:

```text
fixture discovery
→ competition/universe filter
→ model probability
→ bookmaker odds
→ value comparison
→ ranking
→ bulletin generation
```

This screening layer must remain deterministic, production-oriented, and focused on finding current opportunities. It must not perform uncontrolled experimentation or silently alter model/ranking rules.

## 10. Research sector

The Research sector is a separate analytical and experimental layer. Its purpose is to determine **when, why, and under which conditions a detected value signal is reliable**. It is not another name for the Daily Bulletin screening pipeline.

Research must investigate, among other things:

- model calibration and systematic over/underestimation;
- signal quality by market, competition, bookmaker, and time-to-kickoff;
- relationship between initial value, odds movement, and realized CLV;
- bookmaker disagreement and its predictive usefulness;
- effects of lineups, injuries, weather, and other contextual data;
- false-positive value signals and extreme outliers;
- stability of signals across time periods and competitions;
- differences between in-sample, out-of-sample, and walk-forward results;
- model-version and feature-version comparisons;
- whether proposed filters improve signal quality without introducing selection bias.

### 10.1 Research inputs

Research may consume immutable, historically reconstructable data, including:

- fixture and competition records;
- raw and normalized odds snapshots;
- model probabilities and model metadata;
- published pick decision contexts;
- odds trajectories and closing references;
- match outcomes and settlement data;
- lineup, injury, weather, and other contextual observations where available.

Raw observations must be retained separately from derived research metrics.

### 10.2 Research outputs

Research outputs are analytical artifacts, not direct production decisions. They may include:

- calibration reports;
- signal-quality reports;
- CLV and odds-movement analyses;
- backtests and walk-forward evaluations;
- experiment datasets and reproducible notebooks/jobs;
- model or rule proposals;
- documented limitations, biases, and confidence levels.

Every experiment must identify its dataset period, inclusion rules, feature/model versions, evaluation methodology, and result status.

### 10.3 Production boundary

Research must not directly mutate Daily Bulletin behavior. Any change proposed by Research must pass through:

```text
research hypothesis
→ versioned experiment
→ statistical evaluation
→ out-of-sample or walk-forward validation
→ documented acceptance decision
→ explicit production change
→ regression and CI verification
```

Experimental code, datasets, and configurations must be distinguishable from production code and configuration. A research result is not considered production-ready merely because it improves an in-sample metric.

### 10.4 Research acceptance principles

A research proposal should be accepted only when the evidence addresses, as applicable:

- calibration and discrimination quality;
- robustness across time and relevant subgroups;
- leakage and look-ahead bias;
- multiple-testing and overfitting risk;
- data completeness and survivorship bias;
- economic relevance to value and/or CLV;
- reproducibility using stored inputs and explicit versions.

## 11. Dashboard

The dashboard is the operational “eyes” of the system. It must make the complete lifecycle of a pick observable:

- upcoming fixtures and available markets;
- current value opportunities;
- published picks;
- odds history and movement;
- first seen, pick-time, current, and closing odds;
- expected CLV at decision time, where available;
- realized CLV calculated after the event using the valid closing reference;
- data freshness and ingestion health;
- model/version and decision provenance;
- research-derived annotations only when their methodology and version are explicit.

The dashboard should be based on the useful concepts and workflows of the legacy dashboard, but implemented against the new QuantBet data model and production architecture.

## 12. Production requirements

The production system will require, in stages:

- reliable odds and fixture ingestion;
- a canonical quote and market schema;
- persistent odds history, initially expected to use PostgreSQL;
- scheduled and/or continuous workers;
- model execution and versioning;
- value and expected-CLV calculation;
- pick registration;
- post-pick monitoring;
- post-event realized-CLV calculation;
- daily bulletin generation and delivery;
- dashboard/API;
- observability, retries, and data-quality checks;
- deployment and operational configuration.

The research platform will additionally require, in a later stage:

- immutable analytical datasets;
- reproducible experiment execution;
- dataset and feature versioning;
- backtesting and walk-forward evaluation;
- calibration and CLV reporting;
- explicit promotion records from research to production.

## 13. Non-goals for the immediate next step

The immediate next step is **not** to expand model mathematics, build the Research platform, or perform broad refactoring.

The next implementation step should establish the canonical quote/odds-snapshot contract that later ingestion, persistence, value calculation, monitoring, reporting, research, and dashboard components can share.

## 14. Guiding principles

- Preserve raw observations before deriving metrics.
- Make every decision reproducible from stored inputs and model versions.
- Separate current value, expected CLV, realized CLV, and research conclusions.
- Calculate realized CLV only after the event lifecycle provides a valid closing reference.
- Never overwrite odds history when a new snapshot arrives.
- Prefer explicit schemas and contracts over implicit data assumptions.
- Keep Research experimentally isolated from production decision logic.
- Implement one small vertical slice at a time, with tests before moving on.
