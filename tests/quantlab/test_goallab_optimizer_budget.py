import inspect

from h2h.quantlab.goal_lab import model


def test_dc_plus_optimizer_has_iteration_headroom_after_shrinkage() -> None:
    source = inspect.getsource(model._fit_dc_plus)

    assert '"maxiter": 1500' in source
    assert '"ftol": 1e-9' in source
    assert '"gtol": 1e-6' in source
