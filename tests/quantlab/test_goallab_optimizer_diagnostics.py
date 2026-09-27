import inspect

from h2h.quantlab.goal_lab import model


def test_dc_plus_optimizer_failure_logs_diagnostics() -> None:
    source = inspect.getsource(model._fit_dc_plus)

    assert "GoalLab DC+ optimizer failed" in source
    assert "gradient_inf_norm" in source
    assert "parameter_count" in source
    assert "team_count" in source
    assert "league_count" in source
