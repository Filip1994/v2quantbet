# Prediction targeting contract

## Purpose

The production-facing Dixon–Coles boundary binds probabilities to the exact canonical fixture and ordered provider-qualified teams used for model execution. It does not change Dixon–Coles mathematics or acquire training data.

## Identity path

```text
authoritative Fixture
→ PredictionTarget
→ namespace-compatible DixonColesModel
→ FixturePrediction
→ same-canonical-fixture valuation
→ ValuePick
```

`PredictionTarget` is the public read-only interface for the internal immutable target produced by the fixture predictor. It contains the established `ResolvedFixtureIdentity` plus ordered integer home and away team IDs. Its team-ID namespace is derived from the provider fixture reference. The public interface is not constructible. Internal construction requires provider fixture identity and both distinct provider team IDs, and validates canonical/provider fixture consistency through the existing fixture identity machinery. Team names are never identity inputs.

## Model namespace claim

`DixonColesModel.fit()` requires a nonblank `team_id_namespace` and retains it on the fitted model. This is an explicit claim supplied by the training caller. It enables fail-closed namespace comparison but is not evidence of data provenance.

The repository still has no production historical-results acquisition or training adapter for API-Football. Until one supplies authoritative namespaced records, no production-fitted model can claim verified API-Football training provenance.

## Target-bound execution

`DixonColesFixturePredictor.predict()` accepts an authoritative `Fixture`; it has no independent fixture-ID argument. It derives the internal target, rejects equal home/away IDs and namespace mismatch before calling Dixon–Coles, invokes the model with the target's home ID followed by its away ID, and returns the public read-only `FixturePrediction` interface backed by an internal immutable result carrying the same target and a read-only copy of the probabilities.

`PredictionTarget` and `FixturePrediction` expose read-only public interfaces but no supported public constructor or factory. Their concrete result forms and construction functions are internal to the prediction boundary. `evaluate_prediction_quote()` accepts only the concrete result produced by `DixonColesFixturePredictor`. Consequently, ordinary supported public APIs cannot attach arbitrary probabilities, or probabilities copied from a genuine fixture-A prediction, to a fixture-B target. As usual for Python internals, this boundary does not claim protection against deliberate private-module imports, reflection, or object-model abuse.

Low-level Dixon–Coles methods remain available for numerical tests and internal computation. They do not independently provide fixture identity proof.

## Valuation boundary

`evaluate_prediction_quote()` first requires the internal result form produced by the trusted predictor, then rejects unless `prediction.target.fixture_id == quote.fixture_id`. This exact string equality occurs before probability selection. Therefore `api-football:123` does not match `123`, another API-Football fixture, or another provider namespace.

After identity succeeds, the gateway reuses `model_probability_for_selection()` and unchanged `evaluate_value()`. It introduces no new value formula, eligibility rule, staking policy, cross-provider matching, or persistence behavior.
