import inspect

from h2h.quantlab import entrypoint


def test_goallab_validation_preflight_runs_after_dashboard_start_and_before_cycle() -> None:
    source = inspect.getsource(entrypoint.main)

    server_start = source.index("server.start()")
    model_fit = source.index("goal_structural_engine.readiness(")
    preflight = source.index("ensure_latest_goal_model_validation(repository, LOGGER)")
    cycle = source.index("runtime.run_once()")

    assert server_start < model_fit < preflight < cycle
    assert "GoalLab DC+ startup validation failed" in source


def test_dashboard_starts_before_heavy_startup_audits() -> None:
    source = inspect.getsource(entrypoint.main)

    server_start = source.index("server.start()")
    card_audit = source.index("log_cardlab_v5_audit(repository, LOGGER)")
    corner_audit = source.index("log_cornerlab_v2_audit(repository, LOGGER)")

    assert server_start < card_audit
    assert server_start < corner_audit
