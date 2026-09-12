# QuantBet — Product Goals

## 1. Product purpose

QuantBet is a production football value-betting system. Its purpose is to continuously scan upcoming matches, evaluate bookmaker odds against quantitative model probabilities, identify value opportunities, and track the market after a pick is made.

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

The value signal must be kept separate from any prediction about future odds movement.

## 5. Expected CLV signal

The system should estimate whether the selected odds are likely to shorten before the event starts, creating a positive expected closing-line value (CLV).

This is a separate signal from model-vs-bookmaker value:

- **Value** measures the discrepancy between model probability and implied probability.
- **Expected CLV** estimates the likely direction and magnitude of subsequent market movement.

A value opportunity must not automatically be described as a positive-CLV opportunity without a separate basis for that conclusion.

## 6. Pick registry

Every published pick must be registered with immutable decision context, including:

- pick identifier;
- fixture and market/selection;
- model version and configuration;
- model probability;
- bookmaker-implied probability;
- value calculation;
- expected-CLV signal and methodology version;
- odds at pick time;
- pick timestamp;
- applicable filters and decision metadata.

## 7. Post-pick monitoring

After a pick is published, the system must continue collecting and evaluating odds until the event starts or the monitoring window ends.

The monitoring design must support a configurable cadence. An initial candidate cadence is every **30 minutes**, but the final cadence must be defined by system requirements and operational constraints.

The system must record the odds trajectory after publication and calculate realized market movement and CLV when a valid closing reference is available.

## 8. Required odds checkpoints

The dashboard and reporting layer must expose, at minimum, these checkpoints for every tracked pick:

- **First seen odds** — the earliest captured odds for the relevant quote;
- **Pick odds** — the odds at the moment the pick was published;
- **Current odds** — the latest captured odds;
- **Closing odds** — the last valid captured odds before the match starts.

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

The bulletin must clearly distinguish opportunities that are currently actionable from historical or already expired picks.

## 10. Dashboard

The dashboard is the operational “eyes” of the system. It must make the complete lifecycle of a pick observable:

- upcoming fixtures and available markets;
- current value opportunities;
- published picks;
- odds history and movement;
- first seen, pick-time, current, and closing odds;
- realized CLV and related performance metrics;
- data freshness and ingestion health;
- model/version and decision provenance.

The dashboard should be based on the useful concepts and workflows of the legacy dashboard, but implemented against the new QuantBet data model and production architecture.

## 11. Production requirements

The production system will require, in stages:

- reliable odds and fixture ingestion;
- a canonical quote and market schema;
- persistent odds history, initially expected to use PostgreSQL;
- scheduled and/or continuous workers;
- model execution and versioning;
- value and expected-CLV calculation;
- pick registration;
- post-pick monitoring;
- daily bulletin generation and delivery;
- dashboard/API;
- observability, retries, and data-quality checks;
- deployment and operational configuration.

## 12. Non-goals for the immediate next step

The immediate next step is **not** to expand model mathematics or perform broad refactoring.

The next implementation step should establish the canonical quote/odds-snapshot contract that later ingestion, persistence, value calculation, monitoring, reporting, and dashboard components can share.

## 13. Guiding principles

- Preserve raw observations before deriving metrics.
- Make every decision reproducible from stored inputs and model versions.
- Separate current value, expected CLV, and realized CLV.
- Never overwrite odds history when a new snapshot arrives.
- Prefer explicit schemas and contracts over implicit data assumptions.
- Implement one small vertical slice at a time, with tests before moving on.
