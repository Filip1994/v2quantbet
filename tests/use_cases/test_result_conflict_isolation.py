from datetime import UTC, datetime
from types import SimpleNamespace

from h2h.persistence.result_settlement import ResultPersistenceConflictError
from h2h.use_cases.result_settlement import ReconcileFixtureResults


NOW = datetime(2026, 10, 10, tzinfo=UTC)


class Repository:
    def __init__(self):
        self.persisted = []
        self.stable_checked = []

    def reconcile(self, *, reconciled_at):
        return ()

    def claim_due(self, *, claimed_at, limit):
        return ("disputed", "valid")

    def provider_contexts(self, fixture_ids):
        return (("disputed", 1), ("valid", 2))

    def persist_result(self, result, *, checked_at):
        if result.fixture_id == "disputed":
            raise ResultPersistenceConflictError("result contradicts durable fixture identity")
        self.persisted.append(result.fixture_id)

    def stable_result(self, fixture_id, *, as_of):
        self.stable_checked.append(fixture_id)

    def has_due_results(self, *, as_of):
        return False


class Source:
    def fetch(self, contexts):
        return {contexts[0][0]: {"fixture_id": contexts[0][0]}}


def test_conflicting_result_is_not_settled_and_next_fixture_progresses() -> None:
    repository = Repository()
    failures = []
    successes = []
    reconcile = ReconcileFixtureResults(
        repository,  # type: ignore[arg-type]
        Source(),  # type: ignore[arg-type]
        clock=lambda: NOW,
        on_item_failure=lambda fixture, error, at: failures.append((fixture, error, at)),
        on_item_success=successes.append,
    )
    reconcile._normalizer = SimpleNamespace(
        normalize=lambda payload, **_kwargs: SimpleNamespace(fixture_id=payload["fixture_id"])
    )

    cycle = reconcile.execute()

    assert cycle.persisted_result_count == 1
    assert repository.persisted == ["valid"]
    assert repository.stable_checked == ["valid"]
    assert successes == ["valid"]
    assert len(failures) == 1
    assert failures[0][0] == "disputed"
    assert isinstance(failures[0][1], ResultPersistenceConflictError)
    assert failures[0][2] == NOW
    assert cycle.settled_pick_ids == ()
