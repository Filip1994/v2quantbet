    unavailable = lambda _fixture: (_ for _ in ()).throw(
        ActiveModelUnavailableError("missing")
    )
    subject = worker(repository, unavailable, max_items=10)

    cycles = [subject.run_once(), subject.run_once(), subject.run_once()]

    assert [len(cycle.due_fixture_ids) for cycle in cycles] == [10, 10, 5]
    assert [cycle.pending_work for cycle in cycles] == [True, True, False]
    assert [call[0] for call in repository.selection_calls] == [10, 10, 10]
    assert repository.selection_calls[1][1].fixture_id == "api-football:0009"
    assert sum(len(batch) for batch in repository.failure_batches) == 25


def test_wall_budget_advances_cursor_past_examined_normal_fixtures() -> None:
    repository = RepositoryFake(fixtures(6))
    ticks = iter(float(value) for value in range(100))
    subject = worker(
        repository,
        lambda _fixture: None,
        max_items=5,
        max_wall_seconds=2.5,
        monotonic_clock=lambda: next(ticks),
    )

    first = subject.run_once()
    second = subject.run_once()

    assert first.budget_exhausted is True
    assert first.odds_unavailable_fixture_ids == ("api-football:0000",)
    assert repository.selection_calls[0] == (5, None)
    assert repository.selection_calls[1][1] == OpportunityCursor(
        repository.fixtures[0].kickoff_at,
        "api-football:0000",
    )
    assert second.due_fixture_ids[0] == "api-football:0001"


def test_failure_time_is_fresh_for_each_fixture_and_scope_check_is_shared() -> None:
    repository = RepositoryFake(fixtures(2))
    base = datetime(2026, 9, 22, 12, tzinfo=UTC)
    times = iter(base + timedelta(minutes=value) for value in range(5))
    scope_checks: list[str] = []

    def unavailable(fixture):
        scope_checks.append(fixture.fixture_id)
        raise ActiveModelUnavailableError("missing")

    worker(repository, unavailable, clock=lambda: next(times)).run_once()

    failures = repository.failure_batches[0]
    assert scope_checks == ["api-football:0000"]
    assert [failure[3] for failure in failures] == [
        base + timedelta(minutes=2),
        base + timedelta(minutes=4),
    ]

