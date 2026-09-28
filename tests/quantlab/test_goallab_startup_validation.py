import inspect

from h2h.quantlab import entrypoint


def test_goallab_validation_preflight_runs_after_dashboard_start_and_before_cycle() -> None:
    source = inspect.getsource(entrypoint.main)

    server_start = source.index("server.start()")
    preflight = source.index("ensure_latest_goal_model_validation(repository, LOGGER)")
    cycle = source.index("runtime.run_once()")

    assert server_start < preflight < cycle
    assert "GoalLab DC+ startup validation failed" in source
